from __future__ import annotations

import asyncio
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from typing import Any, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.epo import EpoEntry, EpoRawPoll
from app.models.geo import Country, Region
from app.models.molecule import Molecule
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.epo import EpoPollResult

logger = get_logger(__name__)

# EPO OPS namespaces
_OPS_NS = "http://ops.epo.org"
_EXCHANGE_NS = "http://www.epo.org/exchange"

_NS_MAP = {
    "ops": _OPS_NS,
    "exchange": _EXCHANGE_NS,
}


class EpoService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "application/xml",
            },
            timeout=60.0,
            follow_redirects=True,
        )

    async def _fetch_with_retry(self, url: str) -> str:
        """Fetch from EPO OPS with one retry on rate limit or server error."""
        try:
            resp = await self.client.get(url)
            if resp.status_code in (429, 500, 502, 503):
                logger.warning("EPO OPS rate limit/server error; retrying in 5s", status_code=resp.status_code, url=url)
                await asyncio.sleep(5)
                resp = await self.client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as exc:
            logger.error("EPO OPS HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
            raise

    async def close(self) -> None:
        await self.client.aclose()


def _parse_epo_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_text(element: ET.Element | None, path: str, namespaces: dict[str, str]) -> str | None:
    if element is None:
        return None
    child = element.find(path, namespaces)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _extract_applicant(biblio: ET.Element, namespaces: dict[str, str]) -> str | None:
    applicants = biblio.find(".//exchange:applicants", namespaces)
    if applicants is None:
        return None
    for applicant in applicants.findall("exchange:applicant", namespaces):
        addr = applicant.find(".//exchange:addressbook/exchange:name", namespaces)
        if addr is not None and addr.text:
            return addr.text.strip()
    return None


def _extract_inventors(biblio: ET.Element, namespaces: dict[str, str]) -> str | None:
    inventors_el = biblio.find(".//exchange:inventors", namespaces)
    if inventors_el is None:
        return None
    names = []
    for inventor in inventors_el.findall("exchange:inventor", namespaces):
        addr = inventor.find(".//exchange:addressbook/exchange:name", namespaces)
        if addr is not None and addr.text:
            names.append(addr.text.strip())
    return ", ".join(names) if names else None


def _extract_title(biblio: ET.Element, namespaces: dict[str, str]) -> str | None:
    titles = biblio.findall("exchange:invention-title", namespaces)
    for t in titles:
        if t.get("lang") == "en" and t.text:
            return t.text.strip()
    for t in titles:
        if t.text:
            return t.text.strip()
    return None


def _extract_abstract(doc: ET.Element, namespaces: dict[str, str]) -> str | None:
    abstracts = doc.findall("exchange:abstract", namespaces)
    for ab in abstracts:
        if ab.get("lang") == "en":
            texts = ab.findall("exchange:p", namespaces)
            return " ".join(p.text.strip() for p in texts if p.text).strip() or None
    for ab in abstracts:
        texts = ab.findall("exchange:p", namespaces)
        return " ".join(p.text.strip() for p in texts if p.text).strip() or None
    return None


def _extract_publication_info(biblio: ET.Element, namespaces: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    pub_ref = biblio.find("exchange:publication-reference", namespaces)
    if pub_ref is None:
        return None, None, None
    doc_id = pub_ref.find("exchange:document-id", namespaces)
    if doc_id is None:
        return None, None, None
    doc_number = _extract_text(doc_id, "exchange:doc-number", namespaces)
    kind = _extract_text(doc_id, "exchange:kind", namespaces)
    pub_date = _extract_text(doc_id, "exchange:date", namespaces)
    if doc_number and kind:
        pub_number = f"EP{doc_number}{kind}"
    elif doc_number:
        pub_number = f"EP{doc_number}"
    else:
        pub_number = None
    return pub_number, kind, pub_date


def _extract_filing_date(biblio: ET.Element, namespaces: dict[str, str]) -> str | None:
    app_ref = biblio.find("exchange:application-reference", namespaces)
    if app_ref is None:
        return None
    doc_id = app_ref.find("exchange:document-id", namespaces)
    if doc_id is None:
        return None
    return _extract_text(doc_id, "exchange:date", namespaces)


def _parse_epo_xml(xml_text: str) -> list[dict[str, Any]]:
    """Parse EPO OPS XML response into a list of entry dicts."""
    entries: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        logger.error("EPO XML parse error", error=str(exc))
        raise

    # Find all exchange-document nodes
    docs = root.findall(".//exchange:exchange-document", _NS_MAP)
    if not docs:
        # Try without namespace
        docs = root.findall(".//exchange-document")

    for doc in docs:
        biblio = doc.find("exchange:bibliographic-data", _NS_MAP)
        if biblio is None:
            biblio = doc.find("bibliographic-data")
        if biblio is None:
            continue

        pub_number, kind, pub_date_str = _extract_publication_info(biblio, _NS_MAP)
        if not pub_number:
            continue

        title = _extract_title(biblio, _NS_MAP)
        abstract = _extract_abstract(doc, _NS_MAP)
        applicant = _extract_applicant(biblio, _NS_MAP)
        inventors = _extract_inventors(biblio, _NS_MAP)
        filing_date_str = _extract_filing_date(biblio, _NS_MAP)

        pub_date = _parse_epo_date(pub_date_str)
        filing_date = _parse_epo_date(filing_date_str)

        patent_status = "Granted" if kind and kind.startswith("B") else "Application published"

        # EPO URL uses the publication number without kind code
        doc_number_clean = pub_number.replace("EP", "").replace("A1", "").replace("A2", "").replace("A3", "").replace("B1", "").replace("B2", "")
        epo_url = f"https://register.epo.org/application?number=EP{doc_number_clean}"

        entries.append({
            "epo_publication_number": pub_number,
            "title": title or "Unknown",
            "abstract": abstract,
            "applicant": applicant,
            "inventors": inventors,
            "filing_date": filing_date,
            "publication_date": pub_date,
            "patent_status": patent_status,
            "epo_url": epo_url,
        })

    return entries


async def fetch_epo_data(db: AsyncSession) -> EpoPollResult:
    """
    Poll EPO OPS for competitor patent applications and grants,
    upsert into DB, and return a summary result.
    """
    svc = EpoService()
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

    # Build search query
    search_query = (
        'ti=nivolumab OR ti=ipilimumab OR ti=biosimilar OR ti=ABP206 OR '
        'ti=JPB898 OR ti=Xdivane OR ti=HLX18 OR ti=BA1104 OR ti=MB11'
    )
    url = f"{settings.EPO_OPS_BASE_URL}/published-data/search?q={search_query}&Range=1-100"

    try:
        logger.info("EPO OPS query", url=url)
        xml_text = await svc._fetch_with_retry(url)
        await asyncio.sleep(6)  # Stay under 10 requests/minute

        parsed = _parse_epo_xml(xml_text)
        total_found = len(parsed)
        all_parsed_entries = parsed

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            logger.error("EPO OPS authentication required", status_code=exc.response.status_code)
        else:
            logger.error("EPO OPS HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except ET.ParseError as exc:
        logger.error("EPO OPS XML parse error", error=str(exc))
        status = "partial"
        error_message = f"XML parse error: {str(exc)[:500]}"
    except Exception as exc:
        logger.error("EPO OPS fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Upsert raw poll keyed by poll_date
    poll_result = await db.execute(select(EpoRawPoll).where(EpoRawPoll.poll_date == today))
    existing_poll = poll_result.scalar_one_or_none()

    if existing_poll:
        existing_poll.search_query = search_query  # type: ignore[assignment]
        existing_poll.total_count = total_found  # type: ignore[assignment]
        existing_poll.raw_xml = xml_text if status != "failed" else None  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = EpoRawPoll(
            poll_date=today,
            search_query=search_query,
            total_count=total_found,
            raw_xml=xml_text if status != "failed" else None,
            status=status,
            error_message=error_message,
        )
        db.add(raw_poll)

    await db.commit()
    await db.refresh(raw_poll)

    # Upsert entries deduped by epo_publication_number per poll
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_parsed_entries:
        epo_publication_number = entry_data["epo_publication_number"]
        title = entry_data["title"]
        abstract = entry_data.get("abstract")
        applicant = entry_data.get("applicant")
        inventors = entry_data.get("inventors")
        filing_date = entry_data.get("filing_date")
        publication_date = entry_data.get("publication_date")
        patent_status = entry_data.get("patent_status")
        epo_url = entry_data["epo_url"]

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
        applicant_lower = (applicant or "").lower()
        for keyword, comp_id in competitor_keywords.items():
            if keyword in combined or keyword in applicant_lower:
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

        # Check for existing entry (dedup globally by epo_publication_number)
        existing_stmt = select(EpoEntry).where(
            EpoEntry.epo_publication_number == epo_publication_number,
        )
        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.title = title
            existing_entry.abstract = abstract  # type: ignore[assignment]
            existing_entry.applicant = applicant  # type: ignore[assignment]
            existing_entry.inventors = inventors  # type: ignore[assignment]
            existing_entry.filing_date = filing_date  # type: ignore[assignment]
            existing_entry.publication_date = publication_date  # type: ignore[assignment]
            existing_entry.patent_status = patent_status  # type: ignore[assignment]
            existing_entry.patent_type = patent_type  # type: ignore[assignment]
            existing_entry.molecule_id = molecule_id  # type: ignore[assignment]
            existing_entry.competitor_id = competitor_id  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
        else:
            db_entry = EpoEntry(
                raw_poll_id=raw_poll.id,
                epo_publication_number=epo_publication_number,
                title=title,
                abstract=abstract,
                applicant=applicant,
                inventors=inventors,
                filing_date=filing_date,
                publication_date=publication_date,
                patent_status=patent_status,
                epo_url=epo_url,
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

    return EpoPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_date=today,
        status=status,
        total_found=total_found,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_epo_entries(
    raw_poll_id: uuid.UUID, db: AsyncSession
) -> int:
    """
    For every new is_relevant=true entry in the given poll,
    create tier-2 GeoSignals for CEE_EU countries.
    """
    # Find the Europe region
    region_result = await db.execute(
        select(Region).where(Region.code == "CEE_EU")
    )
    region = region_result.scalar_one_or_none()
    if not region:
        logger.warning("CEE_EU region not found; skipping EPO signal creation")
        return 0

    # Fetch all countries in that region
    country_result = await db.execute(
        select(Country).where(Country.region_id == region.id)
    )
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No countries found for CEE_EU region; skipping EPO signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(EpoEntry).where(
            EpoEntry.raw_poll_id == raw_poll_id,
            EpoEntry.is_relevant.is_(True),
            EpoEntry.signals_created_at.is_(None),
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

        _title = f"EP Patent: {entry.title[:80]}..."
        description = (
            f"{entry.applicant or 'Unknown applicant'} filed European patent {entry.epo_publication_number} "
            f"for {entry.patent_type.lower()} related to {target_name}. "
            f"Status: {entry.patent_status}. Publication: {entry.publication_date or 'N/A'}. "
            f"This impacts EU market access strategy."
        )

        for country in countries:
            signal = GeoSignal(
                molecule_id=entry.molecule_id,
                competitor_id=entry.competitor_id,
                region_id=region.id,
                country_ids=[country.id],
                signal_type=SignalType.EP_PATENT,
                confidence=Confidence.PROBABLE,
                relevance_score=85,
                department_tags=["regulatory", "market_access", "legal"],
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=description,
                source_url=entry.epo_url,
                source_type="epo",
                tier=2,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created EPO GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
