from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.ema_epar import EmaEparEntry, EmaEparRawPoll
from app.models.geo import Country, Region
from app.models.molecule import Molecule
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.ema_epar import EmaEparPollResult

logger = get_logger(__name__)


class EmaEparService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "application/json, text/html",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def fetch_medicines_page(self) -> httpx.Response:
        """Fetch the EMA medicines page."""
        return await self.client.get(settings.EMA_EPAR_ENDPOINT)

    async def fetch_json_fallback(self) -> httpx.Response:
        """Fetch the known EMA JSON report endpoint."""
        return await self.client.get(settings.EMA_API_BASE_URL)

    def _parse_date(self, date_str: str | None) -> date | None:
        """Parse DD/MM/YYYY or ISO dates."""
        if not date_str:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _serialize_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert entry dicts to JSON-serializable form."""
        serialized = []
        for entry in entries:
            ser = dict(entry)
            if isinstance(ser.get("decision_date"), date):
                ser["decision_date"] = ser["decision_date"].isoformat()
            serialized.append(ser)
        return serialized

    def parse_json_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse structured JSON from EMA report endpoint."""
        items: list[dict[str, Any]] = data.get("data", [])
        results = []
        for item in items:
            if item.get("biosimilar") != "Yes":
                continue
            decision_date = self._parse_date(
                item.get("european_commission_decision_date")
                or item.get("marketing_authorisation_date")
            )
            results.append({
                "product_name": item.get("name_of_medicine", "").strip(),
                "active_substance": item.get("active_substance", "").strip(),
                "marketing_authorisation_holder": item.get(
                    "marketing_authorisation_developer_applicant_holder", ""
                ).strip(),
                "authorisation_status": item.get("medicine_status", "").strip(),
                "indication": item.get("therapeutic_indication", "").strip() or None,
                "decision_date": decision_date,
                "epar_url": item.get("medicine_url", "").strip(),
            })
        return results

    def parse_html_response(self, html: str) -> tuple[list[dict[str, Any]], str | None]:
        """
        Heuristic HTML parser for EMA medicines search results.
        Also attempts to locate a JSON data link for fallback fetching.
        Returns (entries, json_url_if_found).
        """
        soup = BeautifulSoup(html, "html.parser")
        entries: list[dict[str, Any]] = []

        # Try to find JSON data link in the page
        json_url: str | None = None
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if "medicines_json" in href or "medicines-output" in href:
                json_url = href if href.startswith("http") else f"https://www.ema.europa.eu{href}"
                break

        # Heuristic: look for table rows or medicine cards
        rows = soup.select("table tbody tr, .medicine-item, .views-row")
        for row in rows:
            cells = row.find_all(["td", ".field-content"])
            if not cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            if not texts:
                continue
            # Very loose heuristic: look for EPAR URL
            epar_url = None
            for a in row.find_all("a", href=True):
                a_href = str(a["href"])
                if "/medicines/human/EPAR/" in a_href:
                    epar_url = a_href if a_href.startswith("http") else f"https://www.ema.europa.eu{a_href}"
                    break

            entries.append({
                "product_name": texts[0] if texts else "Unknown",
                "active_substance": texts[1] if len(texts) > 1 else "",
                "marketing_authorisation_holder": texts[2] if len(texts) > 2 else "",
                "authorisation_status": texts[3] if len(texts) > 3 else "",
                "indication": None,
                "decision_date": None,
                "epar_url": epar_url or settings.EMA_EPAR_ENDPOINT,
            })

        return entries, json_url

    async def close(self) -> None:
        await self.client.aclose()


def _match_molecule(
    active_substance: str, molecules: list[Molecule]
) -> Molecule | None:
    """Case-insensitive match on molecule_name or inn."""
    substance_lower = active_substance.lower().strip()
    for mol in molecules:
        if mol.molecule_name and mol.molecule_name.lower().strip() == substance_lower:
            return mol
        if mol.inn and mol.inn.lower().strip() == substance_lower:
            return mol
    return None


def _match_competitor(
    mah: str, competitors: list[Competitor]
) -> Competitor | None:
    """Fuzzy/substring match MAH to competitor canonical_name or parent_company."""
    mah_lower = mah.lower().strip()

    # Exact match first
    for comp in competitors:
        names = [
            comp.canonical_name.lower().strip() if comp.canonical_name else "",
            comp.parent_company.lower().strip() if comp.parent_company else "",
        ]
        for name in names:
            if name and name == mah_lower:
                return comp

    # Substring match
    for comp in competitors:
        names = [
            comp.canonical_name.lower().strip() if comp.canonical_name else "",
            comp.parent_company.lower().strip() if comp.parent_company else "",
        ]
        for name in names:
            if name and (name in mah_lower or mah_lower in name):
                return comp

    return None


async def fetch_ema_epar_data(db: AsyncSession) -> EmaEparPollResult:
    """
    Poll EMA for biosimilar marketing authorisations, upsert into DB,
    and return a summary result.
    """
    svc = EmaEparService()
    today = datetime.now(UTC).date()
    entries_data: list[dict[str, Any]] = []
    status = "success"
    error_message: str | None = None

    try:
        resp = await svc.fetch_medicines_page()
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        if "application/json" in content_type:
            data = resp.json()
            entries_data = svc.parse_json_response(data)
            status = "success"
        else:
            # HTML response
            html_entries, _json_url = svc.parse_html_response(resp.text)

            # Try the known EMA JSON report endpoint for structured data
            try:
                json_resp = await svc.fetch_json_fallback()
                if json_resp.status_code == 200 and "application/json" in json_resp.headers.get("content-type", ""):
                    data = json_resp.json()
                    entries_data = svc.parse_json_response(data)
            except Exception as exc:
                logger.warning("EMA JSON fallback fetch failed", error=str(exc))

            # If fallback didn't yield entries, keep heuristic HTML entries
            if not entries_data and html_entries:
                entries_data = html_entries

            status = "partial"
            error_message = resp.text[:2000]  # Store HTML snippet

    except httpx.HTTPStatusError as exc:
        logger.error("EMA HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except Exception as exc:
        logger.error("EMA fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Upsert raw poll keyed by poll_date
    poll_result = await db.execute(
        select(EmaEparRawPoll).where(EmaEparRawPoll.poll_date == today)
    )
    existing_poll = poll_result.scalar_one_or_none()

    serialized_entries = svc._serialize_entries(entries_data)
    if existing_poll:
        existing_poll.raw_json = {"entries": serialized_entries}  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        existing_poll.endpoint_url = settings.EMA_EPAR_ENDPOINT  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = EmaEparRawPoll(
            poll_date=today,
            endpoint_url=settings.EMA_EPAR_ENDPOINT,
            raw_json={"entries": serialized_entries},
            status=status,
            error_message=error_message,
        )
        db.add(raw_poll)

    await db.commit()
    await db.refresh(raw_poll)

    # Load molecules and competitors for matching
    mol_result = await db.execute(select(Molecule).where(Molecule.is_active.is_(True)))
    molecules = list(mol_result.scalars().all())

    comp_result = await db.execute(select(Competitor).where(Competitor.status == "active"))
    competitors = list(comp_result.scalars().all())

    # Upsert entries deduped by (product_name, decision_date)
    new_entries = 0
    relevant_entries = 0
    for entry_data in entries_data:
        product_name = entry_data.get("product_name", "")
        decision_date = entry_data.get("decision_date")

        if not product_name:
            continue

        molecule = _match_molecule(entry_data.get("active_substance", ""), molecules)
        competitor = _match_competitor(entry_data.get("marketing_authorisation_holder", ""), competitors)
        is_relevant = molecule is not None or competitor is not None

        # Check for existing entry
        existing_stmt = select(EmaEparEntry).where(
            EmaEparEntry.raw_poll_id == raw_poll.id,
            EmaEparEntry.product_name == product_name,
        )
        if decision_date:
            existing_stmt = existing_stmt.where(EmaEparEntry.decision_date == decision_date)
        else:
            existing_stmt = existing_stmt.where(EmaEparEntry.decision_date.is_(None))

        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.authorisation_status = entry_data.get("authorisation_status", "")
            existing_entry.epar_url = entry_data.get("epar_url", "")
            existing_entry.molecule_id = molecule.id if molecule else None  # type: ignore[assignment]
            existing_entry.competitor_id = competitor.id if competitor else None  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
        else:
            db_entry = EmaEparEntry(
                raw_poll_id=raw_poll.id,
                product_name=product_name,
                active_substance=entry_data.get("active_substance", ""),
                marketing_authorisation_holder=entry_data.get("marketing_authorisation_holder", ""),
                authorisation_status=entry_data.get("authorisation_status", ""),
                indication=entry_data.get("indication"),
                decision_date=decision_date,
                epar_url=entry_data.get("epar_url", ""),
                molecule_id=molecule.id if molecule else None,
                competitor_id=competitor.id if competitor else None,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return EmaEparPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_date=today,
        status=status,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_epar_entries(
    raw_poll_id: uuid.UUID, db: AsyncSession
) -> int:
    """
    For every new is_relevant=true entry in the given poll,
    create tier-1 GeoSignals for all countries in the Europe (CEE_EU) region.
    """
    # Find the Europe region
    region_result = await db.execute(
        select(Region).where(Region.code == "CEE_EU")
    )
    region = region_result.scalar_one_or_none()
    if not region:
        logger.warning("CEE_EU region not found; skipping signal creation")
        return 0

    # Fetch all countries in that region
    country_result = await db.execute(
        select(Country).where(Country.region_id == region.id)
    )
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No countries found for CEE_EU region; skipping signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(EmaEparEntry).where(
            EmaEparEntry.raw_poll_id == raw_poll_id,
            EmaEparEntry.is_relevant.is_(True),
            EmaEparEntry.signals_created_at.is_(None),
        )
    )
    entries = list(entry_result.scalars().all())

    signals_created = 0
    now = datetime.now(UTC)
    for entry in entries:
        # Skip if no molecule (shouldn't happen for relevant entries, but safety check)
        if not entry.molecule_id:
            continue

        for country in countries:
            signal = GeoSignal(
                molecule_id=entry.molecule_id,
                competitor_id=entry.competitor_id,
                region_id=region.id,
                country_ids=[country.id],
                signal_type=SignalType.EMA_EPAR_APPROVAL,
                confidence=Confidence.CONFIRMED,
                relevance_score=95,
                department_tags=["commercial", "medical", "regulatory"],
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=None,
                source_url=entry.epar_url,
                source_type="ema_epar",
                tier=1,

            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created EMA EPAR GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
