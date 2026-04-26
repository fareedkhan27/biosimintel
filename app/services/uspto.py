from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.geo import Country
from app.models.molecule import Molecule
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.models.uspto import UsptoEntry, UsptoRawPoll
from app.schemas.uspto import UsptoPollResult

logger = get_logger(__name__)


class UsptoService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "application/json",
            },
            timeout=60.0,
            follow_redirects=True,
        )

    async def _fetch_with_retry(self, url: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch from PatentsView with one retry on rate limit or server error."""
        try:
            resp = await self.client.post(url, json=json_payload)
            if resp.status_code in (429, 500, 502, 503):
                logger.warning("PatentsView rate limit/server error; retrying in 5s", status_code=resp.status_code, url=url)
                await asyncio.sleep(5)
                resp = await self.client.post(url, json=json_payload)
            resp.raise_for_status()
            # Guard against non-JSON responses (e.g., HTML redirect during migration)
            content_type = resp.headers.get("content-type", "")
            if "application/json" not in content_type:
                logger.error("PatentsView returned non-JSON response", content_type=content_type, body=resp.text[:500])
                raise ValueError(f"PatentsView returned non-JSON response (content-type: {content_type}). Service may be down for maintenance.")
            data: dict[str, Any] = resp.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("PatentsView HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
            raise

    async def close(self) -> None:
        await self.client.aclose()


def _parse_patentsview_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_inventors(inventors: list[dict[str, Any]] | None) -> str | None:
    if not inventors:
        return None
    names = []
    for inv in inventors:
        first = (inv.get("inventor_first_name") or "").strip()
        last = (inv.get("inventor_last_name") or "").strip()
        if first and last:
            names.append(f"{last} {first[0]}")
        elif last:
            names.append(last)
        elif first:
            names.append(first)
    return ", ".join(names) if names else None


def _extract_assignee(assignees: list[dict[str, Any]] | None) -> str | None:
    if not assignees:
        return None
    for assignee in assignees:
        org = (assignee.get("assignee_organization") or "").strip()
        if org:
            return org
    return None


async def fetch_uspto_data(db: AsyncSession) -> UsptoPollResult:
    """
    Poll USPTO PatentsView for competitor patent filings,
    upsert into DB, and return a summary result.
    """
    svc = UsptoService()
    today = datetime.now(UTC).date()
    status = "success"
    error_message: str | None = None
    total_found = 0
    all_parsed_entries: list[dict[str, Any]] = []

    # Load molecules and competitors for matching
    mol_result = await db.execute(
        select(Molecule).where(
            Molecule.is_active.is_(True),
            Molecule.molecule_name.in_(["nivolumab", "ipilimumab"]),
        )
    )
    molecules = list(mol_result.scalars().all())

    comp_result = await db.execute(select(Competitor).where(Competitor.status == "active"))
    competitors = list(comp_result.scalars().all())

    # Build molecule map
    molecule_map: dict[str, uuid.UUID] = {}
    for mol in molecules:
        mol_id: uuid.UUID = cast(uuid.UUID, mol.id)
        if mol.molecule_name:
            molecule_map[mol.molecule_name.lower()] = mol_id
        if mol.inn:
            molecule_map[mol.inn.lower()] = mol_id
        if mol.brand_name:
            molecule_map[mol.brand_name.lower()] = mol_id
    if "nivolumab" in molecule_map:
        molecule_map["opdivo"] = molecule_map["nivolumab"]
    if "ipilimumab" in molecule_map:
        molecule_map["yervoy"] = molecule_map["ipilimumab"]

    # Build competitor keyword map
    competitor_keywords: dict[str, uuid.UUID] = {}
    alias_map: dict[str, str] = {
        "abp 206": "ABP 206",
        "jpb898": "JPB898",
        "xdivane": "Xdivane",
        "xbrane": "Xbrane",
        "intas": "Intas",
        "hlx18": "HLX18",
        "henlius": "Henlius",
        "ba1104": "BA1104",
        "boan": "Boan Biotech",
        "mb11": "MB11",
        "mabxience": "mAbxience",
        "reliance": "Reliance Life Sciences",
        "enzene": "Enzene Biosciences",
        "zydus": "Zydus",
        "tishtha": "Tishtha",
        "biocon": "Biocon Biologics",
        "dr. reddy": "Dr. Reddy's",
        "lupin": "Lupin",
        "sandoz": "Sandoz",
        "amgen": "Amgen",
    }

    for comp in competitors:
        cid: uuid.UUID = cast(uuid.UUID, comp.id)
        if comp.canonical_name:
            competitor_keywords[comp.canonical_name.lower().strip()] = cid
        if comp.parent_company:
            competitor_keywords[comp.parent_company.lower().strip()] = cid
        if comp.asset_code:
            competitor_keywords[comp.asset_code.lower().strip()] = cid

    for alias, target_name in alias_map.items():
        target_lower = target_name.lower()
        for comp in competitors:
            names = [
                comp.canonical_name.lower() if comp.canonical_name else "",
                comp.parent_company.lower() if comp.parent_company else "",
                comp.asset_code.lower() if comp.asset_code else "",
            ]
            if any(target_lower in n or n in target_lower for n in names if n):
                competitor_keywords[alias] = cast(uuid.UUID, comp.id)
                break

    query_body: dict[str, Any] = {
        "q": {
            "_or": [
                {"patent_title": {"_text_any": "nivolumab"}},
                {"patent_title": {"_text_any": "ipilimumab"}},
                {"patent_title": {"_text_any": "biosimilar"}},
                {"patent_title": {"_text_any": "ABP 206"}},
                {"patent_title": {"_text_any": "JPB898"}},
                {"patent_title": {"_text_any": "Xdivane"}},
                {"patent_title": {"_text_any": "HLX18"}},
                {"patent_title": {"_text_any": "BA1104"}},
                {"patent_title": {"_text_any": "MB11"}},
                {"patent_abstract": {"_text_any": "nivolumab"}},
                {"patent_abstract": {"_text_any": "ipilimumab"}},
                {"patent_abstract": {"_text_any": "biosimilar"}},
            ]
        },
        "f": [
            "patent_number",
            "patent_title",
            "patent_date",
            "patent_type",
            "assignee_organization",
            "inventor_first_name",
            "inventor_last_name",
            "patent_abstract",
        ],
        "o": {"per_page": 100, "page": 1, "sort": [{"patent_date": "desc"}]},
    }

    try:
        url = f"{settings.USPTO_API_BASE_URL}/patents/query"
        logger.info("PatentsView query", url=url)
        data = await svc._fetch_with_retry(url, query_body)

        patents = data.get("patents", [])
        total_found = data.get("total_patent_count", len(patents))

        for patent in patents:
            patent_number = (patent.get("patent_number") or "").strip()
            title = (patent.get("patent_title") or "").strip()
            if not patent_number or not title:
                continue

            grant_date = _parse_patentsview_date(patent.get("patent_date"))
            assignee = _extract_assignee(patent.get("assignees"))
            inventors = _extract_inventors(patent.get("inventors"))
            abstract = (patent.get("patent_abstract") or "").strip() or None
            patent_url = f"https://patents.google.com/patent/US{patent_number}"

            all_parsed_entries.append({
                "patent_number": patent_number,
                "title": title,
                "abstract": abstract,
                "assignee": assignee,
                "inventors": inventors,
                "grant_date": grant_date,
                "patent_url": patent_url,
            })

    except httpx.HTTPStatusError as exc:
        logger.error("PatentsView HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except Exception as exc:
        logger.error("PatentsView fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Serialize entries for JSON storage
    serializable_entries: list[dict[str, Any]] = []
    for entry in all_parsed_entries:
        ser = dict(entry)
        if isinstance(ser.get("grant_date"), date):
            ser["grant_date"] = ser["grant_date"].isoformat()
        serializable_entries.append(ser)

    # Upsert raw poll keyed by poll_date
    poll_result = await db.execute(select(UsptoRawPoll).where(UsptoRawPoll.poll_date == today))
    existing_poll = poll_result.scalar_one_or_none()

    search_query_str = str(query_body)

    if existing_poll:
        existing_poll.search_query = search_query_str  # type: ignore[assignment]
        existing_poll.total_count = total_found  # type: ignore[assignment]
        existing_poll.raw_json = {"entries": serializable_entries}  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = UsptoRawPoll(
            poll_date=today,
            search_query=search_query_str,
            total_count=total_found,
            raw_json={"entries": serializable_entries},
            status=status,
            error_message=error_message,
        )
        db.add(raw_poll)

    await db.commit()
    await db.refresh(raw_poll)

    # Upsert entries deduped by patent_number per poll
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_parsed_entries:
        patent_number = entry_data["patent_number"]
        title = entry_data["title"]
        abstract = entry_data.get("abstract")
        assignee = entry_data.get("assignee")
        inventors = entry_data.get("inventors")
        grant_date = entry_data.get("grant_date")

        title_lower = title.lower()
        abstract_lower = (abstract or "").lower()
        combined = title_lower + " " + abstract_lower

        # Match molecule
        molecule_id: uuid.UUID | None = None
        for keyword, mol_id in molecule_map.items():
            if keyword in combined:
                molecule_id = mol_id
                break

        # Match competitor
        competitor_id: uuid.UUID | None = None
        assignee_lower = (assignee or "").lower()
        for keyword, comp_id in competitor_keywords.items():
            if keyword in combined or keyword in assignee_lower:
                competitor_id = comp_id
                break

        # Patent type classification
        if any(x in combined for x in ["formulation", "composition", "stable", "buffer"]):
            patent_type = "FORMULATION"
        elif any(x in combined for x in ["process", "manufacturing", "cell culture", "bioreactor", "purification", "chromatography"]):
            patent_type = "PROCESS"
        elif any(x in combined for x in ["device", "delivery", "pen", "injector", "autoinjector", "syringe"]):
            patent_type = "DEVICE"
        elif any(x in combined for x in ["method", "treatment", "indication", "dosing", "regimen", "administration"]):
            patent_type = "METHOD"
        else:
            patent_type = "GENERAL"

        is_relevant = (molecule_id is not None) or (competitor_id is not None)

        # Check for existing entry
        existing_stmt = select(UsptoEntry).where(
            UsptoEntry.raw_poll_id == raw_poll.id,
            UsptoEntry.patent_number == patent_number,
        )
        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.title = title
            existing_entry.abstract = abstract  # type: ignore[assignment]
            existing_entry.assignee = assignee  # type: ignore[assignment]
            existing_entry.inventors = inventors  # type: ignore[assignment]
            existing_entry.grant_date = grant_date  # type: ignore[assignment]
            existing_entry.patent_type = patent_type  # type: ignore[assignment]
            existing_entry.molecule_id = molecule_id  # type: ignore[assignment]
            existing_entry.competitor_id = competitor_id  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
        else:
            db_entry = UsptoEntry(
                raw_poll_id=raw_poll.id,
                patent_number=patent_number,
                title=title,
                abstract=abstract,
                assignee=assignee,
                inventors=inventors,
                grant_date=grant_date,
                patent_url=entry_data["patent_url"],
                molecule_id=molecule_id,
                competitor_id=competitor_id,
                patent_type=patent_type,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return UsptoPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_date=today,
        status=status,
        total_found=total_found,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_uspto_entries(
    raw_poll_id: uuid.UUID, db: AsyncSession
) -> int:
    """
    For every new is_relevant=true entry in the given poll,
    create GeoSignals for all active countries.
    """
    # Fetch all active countries
    country_result = await db.execute(select(Country).where(Country.is_active.is_(True)))
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No active countries found; skipping USPTO signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(UsptoEntry).where(
            UsptoEntry.raw_poll_id == raw_poll_id,
            UsptoEntry.is_relevant.is_(True),
            UsptoEntry.signals_created_at.is_(None),
        )
    )
    entries = list(entry_result.scalars().all())

    signals_created = 0
    now = datetime.now(UTC)

    # Pre-load molecule and competitor names
    molecule_names: dict[uuid.UUID, str] = {}
    competitor_names: dict[uuid.UUID, str] = {}
    for entry in entries:
        if entry.molecule_id and entry.molecule_id not in molecule_names:
            mol_result = await db.execute(select(Molecule).where(Molecule.id == entry.molecule_id))
            mol = mol_result.scalar_one_or_none()
            molecule_names[cast(uuid.UUID, entry.molecule_id)] = str(mol.molecule_name) if mol and mol.molecule_name else "unknown"
        if entry.competitor_id and entry.competitor_id not in competitor_names:
            comp_result = await db.execute(select(Competitor).where(Competitor.id == entry.competitor_id))
            comp = comp_result.scalar_one_or_none()
            competitor_names[cast(uuid.UUID, entry.competitor_id)] = str(comp.canonical_name) if comp and comp.canonical_name else "unknown"

    for entry in entries:
        mol_name = molecule_names.get(cast(uuid.UUID, entry.molecule_id)) if entry.molecule_id else None
        comp_name = competitor_names.get(cast(uuid.UUID, entry.competitor_id)) if entry.competitor_id else None
        target_name = mol_name or comp_name or "unknown"

        if entry.patent_type == "FORMULATION" or entry.patent_type == "PROCESS":
            signal_type = SignalType.PATENT_FILING
            _title = f"US Patent: {entry.title[:80]}..."
            description = (
                f"{entry.assignee or 'Unknown assignee'} filed US patent {entry.patent_number} "
                f"for {entry.patent_type.lower()} related to {target_name}. "
                f"Grant: {entry.grant_date or 'N/A'}. This may impact market entry timing."
            )
            confidence = Confidence.PROBABLE
            tier = 2
            relevance_score = 85
            _tags = ["patent", "ip", "uspto", entry.patent_type.lower()]
            department_tags = ["regulatory", "market_access", "legal"]
        elif entry.patent_type == "METHOD" or entry.patent_type == "DEVICE":
            signal_type = SignalType.PATENT_FILING
            _title = f"US Patent: {entry.title[:80]}..."
            description = (
                f"{entry.assignee or 'Unknown assignee'} filed US patent {entry.patent_number} "
                f"for {entry.patent_type.lower()} related to {target_name}. "
                f"Grant: {entry.grant_date or 'N/A'}."
            )
            confidence = Confidence.PROBABLE
            tier = 3
            relevance_score = 75
            _tags = ["patent", "ip", "uspto", entry.patent_type.lower()]
            department_tags = ["medical", "commercial"]
        else:
            signal_type = SignalType.PATENT_FILING
            _title = f"US Patent: {entry.title[:80]}..."
            description = (
                f"{entry.assignee or 'Unknown assignee'} filed US patent {entry.patent_number} "
                f"for {entry.patent_type.lower()} related to {target_name}. "
                f"Grant: {entry.grant_date or 'N/A'}."
            )
            confidence = Confidence.UNCONFIRMED
            tier = 3
            relevance_score = 70
            _tags = ["patent", "ip", "uspto", entry.patent_type.lower()]
            department_tags = ["medical"]

        for country in countries:
            signal = GeoSignal(
                molecule_id=entry.molecule_id,
                competitor_id=entry.competitor_id,
                region_id=country.region_id,
                country_ids=[country.id],
                signal_type=signal_type,
                confidence=confidence,
                relevance_score=relevance_score,
                department_tags=department_tags,
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=description,
                source_url=entry.patent_url,
                source_type="uspto",
                tier=tier,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created USPTO GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
