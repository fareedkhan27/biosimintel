from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.eu_ctis import EuCtisEntry, EuCtisRawScrape
from app.models.geo import Country, Region
from app.models.molecule import Molecule
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.eu_ctis import EuCtisScrapeResult

logger = get_logger(__name__)

SEARCH_QUERIES = ["nivolumab", "ipilimumab"]
CTIS_SEARCH_URL = f"{settings.EU_CTIS_BASE_URL}/ctis-public/search"
CTIS_VIEW_URL = f"{settings.EU_CTIS_BASE_URL}/ctis-public/view"


def _safe_extract(soup: BeautifulSoup, selectors: list[str], attr: str | None = None, default: str | None = None) -> str | None:
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            if attr:
                val = el.get(attr)
                return str(val) if val is not None else default
            return el.get_text(strip=True)
    return default


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


class EuCtisService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "text/html",
            },
            timeout=60.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def search_ctis(self, query: str, page: int = 1) -> httpx.Response:
        url = f"{CTIS_SEARCH_URL}?lang=en&search={query}&sort=default&pagination={page}"
        return await self.client.get(url)

    def parse_results_page(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        entries: list[dict[str, Any]] = []

        # Detect SPA shell (no server-rendered results)
        if soup.select_one("app-root"):
            logger.warning("CTIS returned SPA shell without server-rendered results")
            return []

        # Try multiple possible result container selectors
        result_rows: list[Any] = []
        for selector in [
            ".result-item",
            ".trial-result",
            ".search-result",
            "table tbody tr",
            ".ctis-result",
            "[data-testid='result-item']",
        ]:
            result_rows = soup.select(selector)
            if result_rows:
                break

        for row in result_rows:
            # CTIS number
            ctis_number = _safe_extract(
                row,
                [".ctis-number", "td:nth-child(1)", ".trial-id", "[data-field='ctisNumber']"],
            )
            if not ctis_number:
                # Try finding it in any link href
                for a in row.find_all("a", href=True):
                    href = str(a["href"])
                    if "/view/" in href:
                        parts = href.split("/view/")
                        if len(parts) > 1:
                            ctis_number = parts[1].split("?")[0].split("#")[0]
                            break

            if not ctis_number:
                continue

            # Title
            trial_title = _safe_extract(
                row,
                ["h3.trial-title", ".result-title a", "td:nth-child(2)", ".trial-title", "[data-field='title']"],
            ) or "Unknown"

            # Sponsor
            sponsor_name = _safe_extract(
                row,
                [".sponsor-name", "td:nth-child(3)", ".sponsor", "[data-field='sponsor']"],
            )

            # Status
            status = _safe_extract(
                row,
                [".trial-status", "td:nth-child(4)", ".status", "[data-field='status']"],
            )

            # Member state
            eu_member_state = _safe_extract(
                row,
                [".member-state", "td:nth-child(5)", ".country", "[data-field='memberState']"],
            )

            # Phase
            phase = _safe_extract(
                row,
                [".trial-phase", ".phase", "td:nth-child(6)", "[data-field='phase']"],
            )

            # Decision date
            decision_date_str = _safe_extract(
                row,
                [".decision-date", ".date", "td:nth-child(7)", "[data-field='decisionDate']"],
            )
            decision_date = _parse_date(decision_date_str)

            # URL
            ctis_url = f"{CTIS_VIEW_URL}/{ctis_number}"
            for a in row.find_all("a", href=True):
                href = str(a["href"])
                if ctis_number in href:
                    ctis_url = href if href.startswith("http") else f"{settings.EU_CTIS_BASE_URL}{href}"
                    break

            entries.append({
                "ctis_number": ctis_number.strip(),
                "trial_title": trial_title.strip(),
                "sponsor_name": sponsor_name.strip() if sponsor_name else None,
                "status": status.strip() if status else None,
                "eu_member_state": eu_member_state.strip() if eu_member_state else None,
                "phase": phase.strip() if phase else None,
                "decision_date": decision_date,
                "intervention": None,
                "condition": None,
                "ctis_url": ctis_url,
            })

        return entries


async def _build_molecule_map(db: AsyncSession) -> dict[str, UUID]:
    result = await db.execute(select(Molecule))
    molecules = result.scalars().all()
    mapping: dict[str, UUID] = {}
    for mol in molecules:
        mid = cast(UUID, mol.id)
        name = cast(str | None, mol.molecule_name)
        brand = cast(str | None, mol.reference_brand)
        inn = cast(str | None, mol.inn)
        if name:
            mapping[name.lower()] = mid
        if brand:
            mapping[brand.lower()] = mid
        if inn:
            mapping[inn.lower()] = mid
        search_terms = cast(list[str] | None, mol.search_terms) or []
        for term in search_terms:
            if term:
                mapping[term.lower()] = mid
    return mapping


async def _build_competitor_map(db: AsyncSession) -> dict[str, UUID]:
    result = await db.execute(select(Competitor))
    competitors = result.scalars().all()
    mapping: dict[str, UUID] = {}
    for comp in competitors:
        cid = cast(UUID, comp.id)
        name = cast(str | None, comp.canonical_name)
        asset = cast(str | None, comp.asset_code)
        parent = cast(str | None, comp.parent_company)
        if name:
            mapping[name.lower()] = cid
        if asset:
            mapping[asset.lower()] = cid
        if parent:
            mapping[parent.lower()] = cid
    return mapping


async def scrape_eu_ctis(db: AsyncSession) -> EuCtisScrapeResult:
    svc = EuCtisService()
    today = datetime.now(UTC).date()
    all_entries: list[dict[str, Any]] = []
    status = "success"
    error_message: str | None = None
    raw_html: str | None = None
    total_results: int | None = None

    try:
        for query in SEARCH_QUERIES:
            if not settings.EU_CTIS_ENABLED:
                logger.info("EU CTIS scraping disabled in settings")
                break

            page = 1
            query_entries: list[dict[str, Any]] = []
            while page <= settings.EU_CTIS_MAX_PAGES:
                try:
                    resp = await svc.search_ctis(query, page)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (403, 429):
                        logger.error(
                            "CTIS blocked scrape",
                            status_code=exc.response.status_code,
                            query=query,
                        )
                        status = "failed"
                        error_message = f"HTTP {exc.response.status_code}: CTIS blocked scraping"
                        break
                    raise

                html = resp.text
                if page == 1 and query == SEARCH_QUERIES[0]:
                    raw_html = html[:70000]  # Store first page HTML for debugging

                entries = svc.parse_results_page(html)
                if not entries:
                    break

                query_entries.extend(entries)

                # Safety: stop if no meaningful results
                if len(entries) == 0:
                    break

                page += 1
                await asyncio.sleep(1.5)  # Be polite between pages

            if status == "failed":
                break

            all_entries.extend(query_entries)

        # Deduplicate by ctis_number
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for entry in all_entries:
            ctis_num = entry["ctis_number"]
            if ctis_num not in seen:
                seen.add(ctis_num)
                deduped.append(entry)
        all_entries = deduped
        total_results = len(all_entries)

        if not all_entries and status != "failed":
            status = "partial"
            if raw_html and "data-critters-container" in raw_html:
                error_message = (
                    "CTIS public portal returned a JavaScript SPA shell without server-rendered results. "
                    "Server-side scraping via BeautifulSoup is not possible against this Angular application. "
                    "Consider using a headless browser or the CTIS API if credentials become available."
                )
            else:
                error_message = "No entries parsed from CTIS HTML; structure may have changed"

    except httpx.HTTPStatusError as exc:
        logger.error("CTIS HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except Exception as exc:
        logger.error("CTIS scrape error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Upsert raw scrape keyed by scrape_date
    scrape_result = await db.execute(
        select(EuCtisRawScrape).where(EuCtisRawScrape.scrape_date == today)
    )
    existing_scrape = scrape_result.scalar_one_or_none()

    portal_url = CTIS_SEARCH_URL
    search_query = ", ".join(SEARCH_QUERIES)

    if existing_scrape:
        existing_scrape.portal_url = portal_url  # type: ignore[assignment]
        existing_scrape.search_query = search_query  # type: ignore[assignment]
        existing_scrape.total_results = total_results  # type: ignore[assignment]
        existing_scrape.raw_html = raw_html  # type: ignore[assignment]
        existing_scrape.status = status  # type: ignore[assignment]
        existing_scrape.error_message = error_message  # type: ignore[assignment]
        raw_scrape = existing_scrape
    else:
        raw_scrape = EuCtisRawScrape(
            scrape_date=today,
            portal_url=portal_url,
            search_query=search_query,
            total_results=total_results,
            raw_html=raw_html,
            status=status,
            error_message=error_message,
        )
        db.add(raw_scrape)

    await db.commit()
    await db.refresh(raw_scrape)

    # Load molecules and competitors for matching
    molecule_map = await _build_molecule_map(db)
    competitor_map = await _build_competitor_map(db)

    # Upsert entries deduped by ctis_number
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_entries:
        ctis_number = entry_data.get("ctis_number", "")
        trial_title = entry_data.get("trial_title", "")
        if not ctis_number or not trial_title:
            continue

        combined = f"{trial_title} {entry_data.get('intervention') or ''} {entry_data.get('condition') or ''} {entry_data.get('sponsor_name') or ''}".lower()

        molecule_id: UUID | None = None
        for kw, mid in molecule_map.items():
            if kw in combined:
                molecule_id = mid
                break

        competitor_id: UUID | None = None
        for kw, cid in competitor_map.items():
            if kw in combined:
                competitor_id = cid
                break

        is_relevant = molecule_id is not None or competitor_id is not None

        existing_stmt = select(EuCtisEntry).where(
            EuCtisEntry.raw_scrape_id == raw_scrape.id,
            EuCtisEntry.ctis_number == ctis_number,
        )
        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.trial_title = trial_title
            existing_entry.sponsor_name = entry_data.get("sponsor_name")  # type: ignore[assignment]
            existing_entry.status = entry_data.get("status")  # type: ignore[assignment]
            existing_entry.eu_member_state = entry_data.get("eu_member_state")  # type: ignore[assignment]
            existing_entry.phase = entry_data.get("phase")  # type: ignore[assignment]
            existing_entry.decision_date = entry_data.get("decision_date")  # type: ignore[assignment]
            existing_entry.ctis_url = entry_data.get("ctis_url", "")
            existing_entry.molecule_id = molecule_id  # type: ignore[assignment]
            existing_entry.competitor_id = competitor_id  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
        else:
            db_entry = EuCtisEntry(
                raw_scrape_id=raw_scrape.id,
                ctis_number=ctis_number,
                sponsor_name=entry_data.get("sponsor_name"),
                trial_title=trial_title,
                intervention=entry_data.get("intervention"),
                condition=entry_data.get("condition"),
                phase=entry_data.get("phase"),
                status=entry_data.get("status"),
                eu_member_state=entry_data.get("eu_member_state"),
                decision_date=entry_data.get("decision_date"),
                ctis_url=entry_data.get("ctis_url", ""),
                molecule_id=molecule_id,
                competitor_id=competitor_id,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return EuCtisScrapeResult(
        scrape_id=raw_scrape.id,  # type: ignore[arg-type]
        scrape_date=today,
        status=status,
        total_results=total_results or 0,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_ctis_entries(
    raw_scrape_id: UUID, db: AsyncSession
) -> int:
    region_result = await db.execute(
        select(Region).where(Region.code == "CEE_EU")
    )
    region = region_result.scalar_one_or_none()
    if not region:
        logger.warning("CEE_EU region not found; skipping signal creation")
        return 0

    country_result = await db.execute(
        select(Country).where(Country.region_id == region.id)
    )
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No countries found for CEE_EU region; skipping signal creation")
        return 0

    entry_result = await db.execute(
        select(EuCtisEntry).where(
            EuCtisEntry.raw_scrape_id == raw_scrape_id,
            EuCtisEntry.is_relevant.is_(True),
            EuCtisEntry.signals_created_at.is_(None),
        )
    )
    entries = list(entry_result.scalars().all())

    signals_created = 0
    now = datetime.now(UTC)
    for entry in entries:
        if not entry.molecule_id:
            continue

        description = (
            f"New trial registered in EU CTIS by {entry.sponsor_name or 'Unknown'}. "
            f"CTIS: {entry.ctis_number}. Phase: {entry.phase or 'N/A'}. "
            f"Status: {entry.status or 'N/A'}. Member State: {entry.eu_member_state or 'N/A'}. "
            f"This is a legally required EU regulatory filing."
        )

        for country in countries:
            signal = GeoSignal(
                molecule_id=entry.molecule_id,
                competitor_id=entry.competitor_id,
                region_id=region.id,
                country_ids=[country.id],
                signal_type=SignalType.EU_CTIS_TRIAL,
                confidence=Confidence.PROBABLE,
                relevance_score=85,
                department_tags=["regulatory", "commercial", "medical"],
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=description,
                source_url=entry.ctis_url,
                source_type="eu_ctis",
                tier=2,
                expires_at=None,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created EU CTIS GeoSignals", count=signals_created, scrape_id=str(raw_scrape_id))
    return signals_created
