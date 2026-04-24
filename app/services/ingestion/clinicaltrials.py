from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.data_provenance import DataProvenance
from app.models.event import Event
from app.models.molecule import Molecule
from app.models.source_document import SourceDocument
from app.services.engine.deduplication import DeduplicationEngine
from app.services.engine.scoring import ScoringEngine
from app.services.engine.verification import VerificationEngine
from app.services.ingestion.sponsor_mapping import SponsorMappingResult, SponsorMappingService

logger = get_logger(__name__)

INDICATION_PATTERNS = {
    "NSCLC": re.compile(r"non.small.cell.lung|cancer.*lung|lung.*cancer|NSCLC", re.I),
    "Melanoma": re.compile(r"melanoma", re.I),
    "RCC": re.compile(r"renal.cell|carcinoma.*renal|kidney.*cancer", re.I),
    "SCCHN": re.compile(r"squamous.cell.*head|head.*neck.*cancer|SCCHN", re.I),
    "ESCC": re.compile(r"esophageal.*squamous|esophagus.*cancer|ESCC", re.I),
}

STAGE_MAP = {
    "early phase 1": "phase_1",
    "phase 1": "phase_1",
    "phase 1/phase 2": "phase_1_2",
    "phase 1/2": "phase_1_2",
    "phase 2": "phase_2",
    "phase 2/phase 3": "phase_3",
    "phase 2/3": "phase_3",
    "phase 3": "phase_3",
    "phase 3b": "phase_3b",
    "phase 4": "launched",
}


class ClinicalTrialsService:
    """Deterministic ingestion from ClinicalTrials.gov — NEVER uses AI for extraction."""

    def __init__(self) -> None:
        self.base_url = str(settings.CLINICALTRIALS_BASE_URL)
        self.client = httpx.AsyncClient(timeout=30.0)
        self.dedup = DeduplicationEngine()
        self.verification = VerificationEngine()
        self.scoring = ScoringEngine()
        self.sponsor_mapping = SponsorMappingService()

    async def sync(self, molecule: Molecule, db: AsyncSession) -> None:
        search_terms: list[str] = molecule.search_terms or [molecule.molecule_name]  # type: ignore[assignment]
        query_term = " OR ".join(search_terms)

        params: dict[str, Any] = {
            "query.term": query_term,
            "pageSize": 100,
        }

        page_token: str | None = None
        total_created = 0
        total_filtered = 0

        canonical_sponsors: set[str] = {c.lower() for c in (molecule.competitor_universe or [])}  # type: ignore[union-attr]

        await self.sponsor_mapping.load_competitors(db, molecule.id)

        while True:
            if page_token:
                params["pageToken"] = page_token

            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            studies = data.get("studies", [])
            for study in studies:
                protocol = study.get("protocolSection", {})
                identification = protocol.get("identificationModule", {})
                title = identification.get("briefTitle", "")
                sponsor = protocol.get("sponsorCollaboratorsModule", {})
                sponsor_name = sponsor.get("leadSponsor", {}).get("name", "")
                sponsor_class = sponsor.get("leadSponsor", {}).get("class", "")

                mapping = self.sponsor_mapping.map_sponsor_to_competitor(
                    sponsor_name, sponsor_class, trial_title=title
                )

                if mapping.blocked:
                    logger.info(
                        "Sponsor blocked by mapping service",
                        sponsor_name=sponsor_name,
                        sponsor_class=sponsor_class,
                        reason=mapping.blocked_reason,
                    )
                    total_filtered += 1
                    continue

                if canonical_sponsors and not self._sponsor_matches(sponsor_name, canonical_sponsors):
                    total_filtered += 1
                    continue

                created = await self._process_study(study, molecule, db, mapping)
                if created:
                    total_created += 1

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            "ClinicalTrials sync completed",
            molecule=molecule.molecule_name,
            created=total_created,
            filtered=total_filtered,
            query=query_term,
        )

    @staticmethod
    def _sponsor_matches(sponsor_name: str, canonical_sponsors: set[str]) -> bool:
        """Check if sponsor name matches any canonical competitor (case-insensitive, substring)."""
        sponsor_lower = sponsor_name.lower().strip()
        if not sponsor_lower:
            return False
        for canonical in canonical_sponsors:
            canonical_lower = canonical.lower().strip()
            if not canonical_lower:
                continue
            if canonical_lower in sponsor_lower or sponsor_lower in canonical_lower:
                return True
        return False

    async def _process_study(
        self,
        study: dict[str, Any],
        molecule: Molecule,
        db: AsyncSession,
        mapping: SponsorMappingResult,
    ) -> bool:
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        sponsor = protocol.get("sponsorCollaboratorsModule", {})
        status_module = protocol.get("statusModule", {})
        description = protocol.get("descriptionModule", {})

        nct_id = identification.get("nctId", "")
        title = identification.get("briefTitle", "")
        sponsor_name = sponsor.get("leadSponsor", {}).get("name", "")

        if not nct_id:
            return False

        url = f"https://clinicaltrials.gov/study/{nct_id}"
        raw_text = f"{title} {description.get('briefSummary', '')}"
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        # Deduplication check by external_id and content_hash
        existing = await db.execute(
            select(SourceDocument).where(
                (SourceDocument.external_id == nct_id) |
                (SourceDocument.content_hash == content_hash)
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Deduplicated study", nct_id=nct_id, content_hash=content_hash)
            return False

        source_doc = SourceDocument(
            source_name="clinicaltrials_gov",
            source_type="clinical_trial",
            external_id=nct_id,
            title=title,
            url=url,
            raw_payload=study,
            raw_text=raw_text,
            content_hash=content_hash,
            processing_status="processing",
            molecule_id=molecule.id,
        )
        db.add(source_doc)
        await db.flush()

        # Extract indication from structured conditions first, then fall back to NLP
        conditions_module = protocol.get("conditionsModule", {})
        conditions = conditions_module.get("conditions", []) or []
        official_title = identification.get("officialTitle", "")

        indication = self._extract_indication(raw_text, conditions, official_title or title)
        indication_priority = (
            molecule.indications.get(indication, {}).get("priority", "LOW")
            if indication
            else "LOW"
        )
        is_pivotal = (
            molecule.indications.get(indication, {}).get("pivotal", False)
            if indication
            else False
        )

        # Extract phase
        phase = (status_module.get("phase", "") or "").lower()
        development_stage = STAGE_MAP.get(phase, "pre_clinical")

        # Create event
        event = Event(
            molecule_id=molecule.id,
            source_document_id=source_doc.id,
            competitor_id=mapping.competitor.id if mapping.competitor else None,
            event_type="clinical_trial",
            event_subtype=phase if phase else None,
            development_stage=development_stage,
            indication=indication,
            indication_priority=indication_priority,
            is_pivotal_indication=is_pivotal,
            country=protocol.get("contactsLocationsModule", {}).get("locations", [{}])[0].get("country") if protocol.get("contactsLocationsModule", {}).get("locations") else None,
            summary=f"Clinical trial {nct_id}: {title}",
            evidence_excerpt=raw_text[:1000],
            verification_status="pending",
            review_status="flagged" if mapping.flag_for_review else "pending",
        )
        db.add(event)
        await db.flush()

        # Provenance
        provenance_records = [
            DataProvenance(
                event_id=event.id,
                source_document_id=source_doc.id,
                field_name="nctId",
                raw_value=nct_id,
                normalized_value=nct_id,
                extraction_method="clinicaltrials_gov",
                confidence=1.0,
            ),
            DataProvenance(
                event_id=event.id,
                source_document_id=source_doc.id,
                field_name="title",
                raw_value=title,
                normalized_value=title,
                extraction_method="clinicaltrials_gov",
                confidence=1.0,
            ),
            DataProvenance(
                event_id=event.id,
                source_document_id=source_doc.id,
                field_name="sponsor",
                raw_value=sponsor_name,
                normalized_value=sponsor_name,
                extraction_method="clinicaltrials_gov",
                confidence=1.0,
            ),
            DataProvenance(
                event_id=event.id,
                source_document_id=source_doc.id,
                field_name="competitor_id",
                raw_value=sponsor_name,
                normalized_value=mapping.competitor.canonical_name if mapping.competitor else None,
                extraction_method=f"sponsor_mapping.{mapping.match_method}" if mapping.match_method else "sponsor_mapping.no_match",
                confidence=mapping.confidence,
            ),
        ]
        for p in provenance_records:
            db.add(p)

        # Verify
        from app.services.engine.verification import RejectedEvent, VerifiedEvent
        result = self.verification.verify(event, provenance_records)
        if isinstance(result, VerifiedEvent):
            event.verification_status = "verified"  # type: ignore[assignment]
            event.verification_confidence = result.confidence  # type: ignore[assignment]
            event.verified_sources_count = len(result.sources)  # type: ignore[assignment]
        elif isinstance(result, RejectedEvent):
            event.verification_status = "rejected"  # type: ignore[assignment]
            event.verification_confidence = 0.0  # type: ignore[assignment]

        # Score
        scored = self.scoring.score(event)
        event.threat_score = scored["threat_score"]
        event.traffic_light = scored["traffic_light"]
        event.score_breakdown = scored["breakdown"]

        source_doc.processing_status = "completed"  # type: ignore[assignment]
        return True

    def _extract_indication(
        self,
        text: str,
        conditions: list[str] | None = None,
        title: str = "",
    ) -> str | None:
        """Extract indication from CT.gov structured data or free text.

        Priority:
        1. Structured ``conditions`` array from CT.gov API.
        2. Regex patterns over ``title + text`` (OfficialTitle / BriefTitle + summary).
        """
        # 1. Structured conditions array from CT.gov
        if conditions:
            for condition in conditions:
                for name, pattern in INDICATION_PATTERNS.items():
                    if pattern.search(condition):
                        return name
            # No pattern match — return first condition as best-effort fallback
            return conditions[0]

        # 2. NLP fallback over title + text
        full_text = f"{title} {text}".strip()
        if full_text:
            for name, pattern in INDICATION_PATTERNS.items():
                if pattern.search(full_text):
                    return name

        return None

    async def close(self) -> None:
        await self.client.aclose()
