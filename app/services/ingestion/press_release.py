from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.data_provenance import DataProvenance
from app.models.event import Event
from app.models.source_document import SourceDocument
from app.services.engine.scoring import ScoringEngine
from app.services.engine.verification import RejectedEvent, VerificationEngine, VerifiedEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.molecule import Molecule

logger = get_logger(__name__)


class PressReleaseService:
    """Deterministic ingestion of press release text."""

    def __init__(self) -> None:
        self.verification = VerificationEngine()
        self.scoring = ScoringEngine()

    async def ingest(
        self,
        text: str,
        source_url: str,
        molecule: Molecule,
        db: AsyncSession,
    ) -> None:
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        # Deduplication check by content_hash
        existing = await db.execute(
            select(SourceDocument).where(SourceDocument.content_hash == content_hash)
        )
        if existing.scalar_one_or_none():
            logger.info("Deduplicated press release", content_hash=content_hash)
            return

        source_doc = SourceDocument(
            source_name="company_ir",
            source_type="press_release",
            title=text[:200],
            url=source_url,
            raw_text=text,
            content_hash=content_hash,
            processing_status="processing",
            molecule_id=molecule.id,
        )
        db.add(source_doc)
        await db.flush()

        event = Event(
            molecule_id=molecule.id,
            source_document_id=source_doc.id,
            event_type="press_release",
            summary=text[:500],
            evidence_excerpt=text[:1000],
            verification_status="pending",
        )
        db.add(event)
        await db.flush()

        provenance = [
            DataProvenance(
                event_id=event.id,
                source_document_id=source_doc.id,
                field_name="text",
                raw_value=text,
                normalized_value=text[:1000],
                extraction_method="company_ir",
                confidence=0.85,
            ),
        ]
        for p in provenance:
            db.add(p)

        result = self.verification.verify(event, provenance)
        if isinstance(result, VerifiedEvent):
            event.verification_status = "verified"  # type: ignore[assignment]
            event.verification_confidence = result.confidence  # type: ignore[assignment]
            event.verified_sources_count = len(result.sources)  # type: ignore[assignment]
        elif isinstance(result, RejectedEvent):
            event.verification_status = "rejected"  # type: ignore[assignment]
            event.verification_confidence = 0.0  # type: ignore[assignment]

        scored = self.scoring.score(event)
        event.threat_score = scored["threat_score"]
        event.traffic_light = scored["traffic_light"]
        event.score_breakdown = scored["breakdown"]

        source_doc.processing_status = "completed"  # type: ignore[assignment]
        logger.info("Press release ingested", molecule=molecule.molecule_name)
