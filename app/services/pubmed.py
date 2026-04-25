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
from app.models.geo import Country
from app.models.molecule import Molecule
from app.models.pubmed import PubmedEntry, PubmedRawPoll
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.pubmed import PubmedPollResult

logger = get_logger(__name__)

# Base search terms that are always included
_BASE_SEARCH_TERMS = [
    "nivolumab[Title/Abstract]",
    "ipilimumab[Title/Abstract]",
]

# Known competitor product codes to always include in search
_KNOWN_PRODUCT_CODES = [
    "ABP 206[Title/Abstract]",
    "JPB898[Title/Abstract]",
    "Xdivane[Title/Abstract]",
    "HLX18[Title/Abstract]",
]


class PubmedService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "application/json",
            },
            timeout=60.0,
            follow_redirects=True,
        )
        self.rate_limit_delay = 0.15 if settings.PUBMED_API_KEY else 0.4

    async def _fetch_with_retry(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch from NCBI E-utilities with one retry on rate limit or server error."""
        try:
            await asyncio.sleep(self.rate_limit_delay)
            resp = await self.client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503):
                logger.warning("NCBI rate limit/server error; retrying in 5s", status_code=resp.status_code, url=url)
                await asyncio.sleep(5)
                await asyncio.sleep(self.rate_limit_delay)
                resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("NCBI HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
            raise

    async def _fetch_xml_with_retry(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Fetch XML from NCBI E-utilities with one retry on rate limit or server error."""
        try:
            await asyncio.sleep(self.rate_limit_delay)
            resp = await self.client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503):
                logger.warning("NCBI XML rate limit/server error; retrying in 5s", status_code=resp.status_code, url=url)
                await asyncio.sleep(5)
                await asyncio.sleep(self.rate_limit_delay)
                resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as exc:
            logger.error("NCBI XML HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
            raise

    async def close(self) -> None:
        await self.client.aclose()


def _build_search_query(_molecules: list[Molecule], competitors: list[Competitor]) -> str:
    """Build Entrez search query from molecules and competitors."""
    terms = set(_BASE_SEARCH_TERMS)

    # Add competitor asset codes
    for comp in competitors:
        if comp.asset_code:
            code = comp.asset_code.strip()
            if code:
                terms.add(f"{code}[Title/Abstract]")

    return " OR ".join(sorted(terms))


def _build_competitor_keyword_map(competitors: list[Competitor]) -> dict[str, uuid.UUID]:
    """Build a keyword -> competitor_id map for classification."""
    keyword_map: dict[str, uuid.UUID] = {}

    for comp in competitors:
        cid: uuid.UUID = cast(uuid.UUID, comp.id)
        # Canonical name
        if comp.canonical_name:
            keyword_map[comp.canonical_name.lower().strip()] = cid
        # Parent company
        if comp.parent_company:
            keyword_map[comp.parent_company.lower().strip()] = cid
        # Asset code
        if comp.asset_code:
            keyword_map[comp.asset_code.lower().strip()] = cid

    # Add known aliases that may not match canonical names exactly
    aliases: dict[str, str] = {
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

    for alias, target_name in aliases.items():
        target_lower = target_name.lower()
        for comp in competitors:
            names = [
                comp.canonical_name.lower() if comp.canonical_name else "",
                comp.parent_company.lower() if comp.parent_company else "",
                comp.asset_code.lower() if comp.asset_code else "",
            ]
            if any(target_lower in n or n in target_lower for n in names if n):
                keyword_map[alias] = cast(uuid.UUID, comp.id)
                break

    return keyword_map


def _parse_esearch(data: dict[str, Any]) -> tuple[list[str], int]:
    """Parse ESearch response. Returns (pmid_list, total_count)."""
    esearchresult = data.get("esearchresult", {})
    count = int(esearchresult.get("count", "0"))
    idlist = esearchresult.get("idlist", [])
    return idlist, count


def _parse_pub_date(date_str: str | None) -> date | None:
    """Parse PubMed date string to date. Handles 'YYYY Mon DD', 'YYYY/MM/DD', etc."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Try ISO-like first
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y %b %d", "%b %Y", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Try sortpubdate which may have time: "2026/04/23 00:00"
    if " " in date_str:
        try:
            return datetime.strptime(date_str.split(" ")[0], "%Y/%m/%d").date()
        except ValueError:
            pass
    return None


def _extract_doi(articleids: list[dict[str, Any]], elocationid: str | None) -> str | None:
    """Extract DOI from articleids or elocationid."""
    if elocationid and "doi:" in elocationid.lower():
        parts = elocationid.split("doi:")
        if len(parts) > 1:
            return parts[1].strip()
    for aid in articleids:
        if aid.get("idtype") == "doi":
            return aid.get("value")
    return None


def _extract_authors(authors: list[dict[str, Any]] | None) -> str | None:
    """Join authors as 'Smith J, Jones A'."""
    if not authors:
        return None
    names = [a.get("name", "").strip() for a in authors if a.get("name")]
    return ", ".join(names) if names else None


def _parse_esummary_article(uid: str, article: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single ESummary article dict."""
    title = article.get("title", "").strip()
    if not title:
        return None

    pub_date = _parse_pub_date(article.get("sortpubdate") or article.get("pubdate"))
    journal = article.get("fulljournalname") or article.get("source")
    authors = _extract_authors(article.get("authors"))
    doi = _extract_doi(article.get("articleids", []), article.get("elocationid"))

    return {
        "pmid": uid,
        "doi": doi,
        "title": title,
        "journal": journal,
        "pub_date": pub_date,
        "authors": authors,
        "article_url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
    }


def _should_fetch_abstract(title: str, competitor_keywords: dict[str, uuid.UUID]) -> bool:
    """Only fetch abstracts for articles that mention competitor keywords."""
    title_lower = title.lower()
    for keyword in competitor_keywords:
        if keyword in title_lower:
            return True
    # Also fetch if title contains biosimilar-related terms
    biosim_terms = ["biosimilar", "generic", "follow-on", "copy"]
    return any(term in title_lower for term in biosim_terms)


def _extract_abstract_from_xml(xml_text: str) -> str | None:
    """Extract abstract text from PubMed EFetch XML."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        abstract_texts = []
        for abst in root.iter("AbstractText"):
            label = abst.get("Label", "")
            text = (abst.text or "").strip()
            if text:
                if label:
                    abstract_texts.append(f"{label}: {text}")
                else:
                    abstract_texts.append(text)
        return "\n".join(abstract_texts) if abstract_texts else None
    except ET.ParseError as exc:
        logger.warning("Failed to parse PubMed XML abstract", error=str(exc))
        return None


def _classify_article(
    title: str,
    abstract: str | None,
    molecule_map: dict[str, uuid.UUID],
    competitor_keywords: dict[str, uuid.UUID],
) -> tuple[uuid.UUID | None, uuid.UUID | None, str, bool]:
    """Classify article and return (molecule_id, competitor_id, publication_type, is_relevant)."""
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
    for keyword, comp_id in competitor_keywords.items():
        if keyword in combined:
            competitor_id = comp_id
            break

    # Publication type classification
    if any(x in combined for x in ["phase 3", "phase iii", "pivotal", "randomized controlled trial", "efficacy"]):
        publication_type = "PHASE3_READOUT"
    elif any(x in combined for x in ["adverse event", "safety", "toxicity", "immunogenicity", "serious adverse"]):
        publication_type = "SAFETY_SIGNAL"
    elif any(x in combined for x in ["real-world", "real world", "rwe", "observational", "registry", "retrospective"]):
        publication_type = "RWE"
    else:
        publication_type = "GENERAL"

    is_relevant = (molecule_id is not None) or (competitor_id is not None)
    return molecule_id, competitor_id, publication_type, is_relevant


async def fetch_pubmed_data(db: AsyncSession) -> PubmedPollResult:
    """
    Poll PubMed/Entrez for recent publications, upsert into DB,
    and return a summary result.
    """
    svc = PubmedService()
    today = datetime.now(UTC).date()
    status = "success"
    error_message: str | None = None
    total_found = 0
    all_parsed_entries: list[dict[str, Any]] = []

    # Load molecules and competitors for query building and matching
    mol_result = await db.execute(
        select(Molecule).where(
            Molecule.is_active.is_(True),
            Molecule.molecule_name.in_(["nivolumab", "ipilimumab"]),
        )
    )
    molecules = list(mol_result.scalars().all())

    comp_result = await db.execute(
        select(Competitor).where(Competitor.status == "active")
    )
    competitors = list(comp_result.scalars().all())

    # Build maps for classification
    molecule_map: dict[str, uuid.UUID] = {}
    for mol in molecules:
        mol_id: uuid.UUID = cast(uuid.UUID, mol.id)
        if mol.molecule_name:
            molecule_map[mol.molecule_name.lower()] = mol_id
        if mol.inn:
            molecule_map[mol.inn.lower()] = mol_id
        if mol.brand_name:
            molecule_map[mol.brand_name.lower()] = mol_id
    # Add common brand names
    if "nivolumab" in molecule_map:
        molecule_map["opdivo"] = molecule_map["nivolumab"]
    if "ipilimumab" in molecule_map:
        molecule_map["yervoy"] = molecule_map["ipilimumab"]

    competitor_keywords = _build_competitor_keyword_map(competitors)

    # Build search query
    search_query = _build_search_query(molecules, competitors)

    try:
        # Step 1: ESearch
        esearch_url = f"{settings.PUBMED_API_BASE_URL}/esearch.fcgi"
        esearch_params = {
            "db": "pubmed",
            "term": search_query,
            "retmax": 100,
            "sort": "date",
            "retmode": "json",
            "datetype": "pdat",
            "reldate": settings.PUBMED_LOOKBACK_DAYS,
        }
        if settings.PUBMED_API_KEY:
            esearch_params["api_key"] = settings.PUBMED_API_KEY

        logger.info("PubMed ESearch", query=search_query)
        esearch_data = await svc._fetch_with_retry(esearch_url, esearch_params)
        pmids, total_found = _parse_esearch(esearch_data)

        if not pmids:
            logger.info("PubMed ESearch returned no results")
        else:
            # Step 2: ESummary in batches of 200
            batch_size = 200
            esummary_url = f"{settings.PUBMED_API_BASE_URL}/esummary.fcgi"

            for i in range(0, len(pmids), batch_size):
                batch = pmids[i:i + batch_size]
                id_str = ",".join(batch)
                esummary_params = {
                    "db": "pubmed",
                    "id": id_str,
                    "retmode": "json",
                }
                if settings.PUBMED_API_KEY:
                    esummary_params["api_key"] = settings.PUBMED_API_KEY

                logger.info("PubMed ESummary batch", batch=len(batch), start=i)
                esummary_data = await svc._fetch_with_retry(esummary_url, esummary_params)
                result = esummary_data.get("result", {})

                for uid in batch:
                    article = result.get(uid)
                    if not article or not isinstance(article, dict):
                        continue
                    parsed = _parse_esummary_article(uid, article)
                    if parsed:
                        all_parsed_entries.append(parsed)

            # Step 3: Selective EFetch for abstracts
            efetch_url = f"{settings.PUBMED_API_BASE_URL}/efetch.fcgi"
            for entry in all_parsed_entries:
                if _should_fetch_abstract(entry["title"], competitor_keywords):
                    efetch_params = {
                        "db": "pubmed",
                        "id": entry["pmid"],
                        "retmode": "xml",
                    }
                    if settings.PUBMED_API_KEY:
                        efetch_params["api_key"] = settings.PUBMED_API_KEY

                    try:
                        xml_text = await svc._fetch_xml_with_retry(efetch_url, efetch_params)
                        abstract = _extract_abstract_from_xml(xml_text)
                        entry["abstract"] = abstract
                    except Exception as exc:
                        logger.warning("PubMed EFetch failed for PMID", pmid=entry["pmid"], error=str(exc))

    except httpx.HTTPStatusError as exc:
        logger.error("PubMed HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except Exception as exc:
        logger.error("PubMed fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Upsert raw poll keyed by poll_date
    poll_result = await db.execute(
        select(PubmedRawPoll).where(PubmedRawPoll.poll_date == today)
    )
    existing_poll = poll_result.scalar_one_or_none()

    raw_payload: dict[str, Any] = {"entries": all_parsed_entries}
    # Ensure esearch_data exists in scope
    try:
        raw_payload["esearch"] = esearch_data
    except NameError:
        raw_payload["esearch"] = {}

    # Serialize dates for JSON storage
    serializable_entries = []
    for entry in all_parsed_entries:
        ser = dict(entry)
        if isinstance(ser.get("pub_date"), date):
            ser["pub_date"] = ser["pub_date"].isoformat()
        serializable_entries.append(ser)
    raw_payload["entries"] = serializable_entries

    if existing_poll:
        existing_poll.search_query = search_query  # type: ignore[assignment]
        existing_poll.total_count = total_found  # type: ignore[assignment]
        existing_poll.raw_json = raw_payload  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = PubmedRawPoll(
            poll_date=today,
            search_query=search_query,
            total_count=total_found,
            raw_json=raw_payload,
            status=status,
            error_message=error_message,
        )
        db.add(raw_poll)

    await db.commit()
    await db.refresh(raw_poll)

    # Upsert entries deduped by pmid per poll
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_parsed_entries:
        pmid = entry_data["pmid"]
        title = entry_data["title"]
        abstract = entry_data.get("abstract")

        molecule_id, competitor_id, publication_type, is_relevant = _classify_article(
            title, abstract, molecule_map, competitor_keywords
        )

        # Check for existing entry in this poll
        existing_stmt = select(PubmedEntry).where(
            PubmedEntry.raw_poll_id == raw_poll.id,
            PubmedEntry.pmid == pmid,
        )
        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.title = title
            existing_entry.abstract = abstract  # type: ignore[assignment]
            existing_entry.publication_type = publication_type  # type: ignore[assignment]
            existing_entry.molecule_id = molecule_id  # type: ignore[assignment]
            existing_entry.competitor_id = competitor_id  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
            existing_entry.doi = entry_data.get("doi")  # type: ignore[assignment]
            existing_entry.authors = entry_data.get("authors")  # type: ignore[assignment]
            existing_entry.journal = entry_data.get("journal")  # type: ignore[assignment]
            existing_entry.pub_date = entry_data.get("pub_date")  # type: ignore[assignment]
        else:
            db_entry = PubmedEntry(
                raw_poll_id=raw_poll.id,
                pmid=pmid,
                doi=entry_data.get("doi"),
                title=title,
                abstract=abstract,
                authors=entry_data.get("authors"),
                journal=entry_data.get("journal"),
                pub_date=entry_data.get("pub_date"),
                article_url=entry_data["article_url"],
                molecule_id=molecule_id,
                competitor_id=competitor_id,
                publication_type=publication_type,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return PubmedPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_date=today,
        status=status,
        total_found=total_found,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_pubmed_entries(
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
        logger.warning("No active countries found; skipping signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(PubmedEntry).where(
            PubmedEntry.raw_poll_id == raw_poll_id,
            PubmedEntry.is_relevant.is_(True),
            PubmedEntry.signals_created_at.is_(None),
        )
    )
    entries = list(entry_result.scalars().all())

    signals_created = 0
    now = datetime.now(UTC)

    # Pre-load molecule names
    molecule_names: dict[uuid.UUID, str] = {}
    for entry in entries:
        if entry.molecule_id and entry.molecule_id not in molecule_names:
            mol_result = await db.execute(
                select(Molecule).where(Molecule.id == entry.molecule_id)
            )
            mol = mol_result.scalar_one_or_none()
            molecule_names[cast(uuid.UUID, entry.molecule_id)] = str(mol.molecule_name) if mol and mol.molecule_name else "unknown"

    for entry in entries:
        if not entry.molecule_id:
            continue

        mol_name = molecule_names.get(cast(uuid.UUID, entry.molecule_id), "unknown")

        if entry.publication_type == "PHASE3_READOUT":
            signal_type = SignalType.PUBLICATION_PHASE3
            _title = f"Phase III Readout: {entry.title[:80]}..."
            description = (
                f"New Phase III publication for "
                f"{mol_name} "
                f"in {entry.journal or 'unknown journal'}. "
                f"PMID: {entry.pmid}. "
                f"{'Abstract indicates pivotal efficacy data.' if entry.abstract and 'efficacy' in entry.abstract.lower() else 'Review for clinical implications.'}"
            )
            confidence = Confidence.PROBABLE
            tier = 2
            relevance_score = 85
            _tags = ["publication", "phase3", "clinical", "efficacy"]
            department_tags = ["medical", "commercial"]
        elif entry.publication_type == "SAFETY_SIGNAL":
            signal_type = SignalType.PUBLICATION_SAFETY
            _title = f"Safety Signal: {entry.title[:80]}..."
            description = (
                f"New safety publication for "
                f"{mol_name} "
                f"in {entry.journal or 'unknown journal'}. "
                f"PMID: {entry.pmid}. Review for adverse event implications."
            )
            confidence = Confidence.PROBABLE
            tier = 2
            relevance_score = 85
            _tags = ["publication", "safety", "adverse_event", "medical"]
            department_tags = ["medical", "regulatory"]
        elif entry.publication_type == "RWE":
            signal_type = SignalType.PUBLICATION_RWE
            _title = f"RWE Publication: {entry.title[:80]}..."
            description = (
                f"New real-world evidence publication for "
                f"{mol_name} "
                f"in {entry.journal or 'unknown journal'}. "
                f"PMID: {entry.pmid}."
            )
            confidence = Confidence.PROBABLE
            tier = 3
            relevance_score = 75
            _tags = ["publication", "rwe", "observational"]
            department_tags = ["medical", "commercial"]
        else:
            signal_type = SignalType.PUBLICATION_GENERAL
            _title = f"Publication: {entry.title[:80]}..."
            description = (
                f"New publication for "
                f"{mol_name} "
                f"in {entry.journal or 'unknown journal'}. "
                f"PMID: {entry.pmid}."
            )
            confidence = Confidence.UNCONFIRMED
            tier = 3
            relevance_score = 70
            _tags = ["publication", "research"]
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
                source_url=entry.article_url,
                source_type="pubmed",
                tier=tier,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created PubMed GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
