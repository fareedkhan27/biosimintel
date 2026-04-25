from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.geo import Country
from app.models.molecule import Molecule
from app.models.openfda import OpenfdaEntry, OpenfdaRawPoll
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.openfda import OpenfdaPollResult

logger = get_logger(__name__)

# Known competitor product codes to watch for
_KNOWN_PRODUCT_CODES = {"abp 206", "abp206", "jpb898", "xdivane", "hlx18"}


class OpenfdaService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def _fetch_with_retry(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch from openFDA with one exponential backoff retry on rate limit."""
        try:
            resp = await self.client.get(url, params=params)
            if resp.status_code == 429:
                logger.warning("openFDA rate limit hit; retrying in 2s", url=url)
                await asyncio.sleep(2)
                resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # openFDA returns 404 with JSON error body for no matches
                try:
                    err_data: dict[str, Any] = exc.response.json()
                    return err_data
                except Exception:
                    return {"error": {"code": "NOT_FOUND", "message": exc.response.text}}
            raise

    async def close(self) -> None:
        await self.client.aclose()


def _match_molecule(
    generic_name: str | None, molecules: list[Molecule]
) -> Molecule | None:
    """Case-insensitive match on molecule_name or inn."""
    if not generic_name:
        return None
    name_lower = generic_name.lower().strip()
    for mol in molecules:
        if mol.molecule_name and mol.molecule_name.lower().strip() == name_lower:
            return mol
        if mol.inn and mol.inn.lower().strip() == name_lower:
            return mol
    return None


def _match_competitor(
    manufacturer: str | None, competitors: list[Competitor]
) -> Competitor | None:
    """Fuzzy/substring match manufacturer to competitor canonical_name or parent_company."""
    if not manufacturer:
        return None
    manu_lower = manufacturer.lower().strip()

    # Exact match first
    for comp in competitors:
        names = [
            comp.canonical_name.lower().strip() if comp.canonical_name else "",
            comp.parent_company.lower().strip() if comp.parent_company else "",
        ]
        for name in names:
            if name and name == manu_lower:
                return comp

    # Substring match
    for comp in competitors:
        names = [
            comp.canonical_name.lower().strip() if comp.canonical_name else "",
            comp.parent_company.lower().strip() if comp.parent_company else "",
        ]
        for name in names:
            if name and (name in manu_lower or manu_lower in name):
                return comp

    return None


def _brand_matches_known_code(brand_name: str | None) -> bool:
    if not brand_name:
        return False
    return brand_name.lower().strip().replace(" ", "") in _KNOWN_PRODUCT_CODES


def _parse_fda_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_drugsfda_entries(data: dict[str, Any], _endpoint_url: str) -> list[dict[str, Any]]:
    """Parse drugsfda.json results into normalized entry dicts."""
    results: list[dict[str, Any]] = []
    for result in data.get("results", []):
        app_num = result.get("application_number")
        sponsor = result.get("sponsor_name", "").strip() or None
        submissions = result.get("submissions", [])
        products = result.get("products", [])

        if products:
            for prod in products:
                brand = prod.get("brand_name", "").strip() or None
                generic = prod.get("generic_name", "").strip() or None
                is_biosimilar = prod.get("biosimilar") == "Y"
                product_type = "BIOSIMILAR" if is_biosimilar else "BLA"
                openfda_url = f'{settings.OPENFDA_API_BASE_URL}/drug/drugsfda.json?search=application_number:"{app_num}"' if app_num else None

                if submissions:
                    for sub in submissions:
                        sub_status = sub.get("submission_status", "").strip() or None
                        sub_type = sub.get("submission_type", "").strip() or None
                        status_date = _parse_fda_date(sub.get("submission_status_date"))

                        results.append({
                            "application_number": app_num,
                            "brand_name": brand,
                            "generic_name": generic,
                            "manufacturer_name": sponsor,
                            "product_type": product_type,
                            "submission_type": sub_type,
                            "submission_status": sub_status,
                            "approval_date": status_date,
                            "openfda_url": openfda_url,
                        })
                else:
                    results.append({
                        "application_number": app_num,
                        "brand_name": brand,
                        "generic_name": generic,
                        "manufacturer_name": sponsor,
                        "product_type": product_type,
                        "submission_type": None,
                        "submission_status": None,
                        "approval_date": None,
                        "openfda_url": openfda_url,
                    })
        else:
            # No products — capture application-level info
            openfda_url = f'{settings.OPENFDA_API_BASE_URL}/drug/drugsfda.json?search=application_number:"{app_num}"' if app_num else None
            results.append({
                "application_number": app_num,
                "brand_name": None,
                "generic_name": None,
                "manufacturer_name": sponsor,
                "product_type": "BLA",
                "submission_type": None,
                "submission_status": None,
                "approval_date": None,
                "openfda_url": openfda_url,
            })

    return results


def _extract_label_entries(data: dict[str, Any], _endpoint_url: str) -> list[dict[str, Any]]:
    """Parse label.json results into normalized entry dicts."""
    results: list[dict[str, Any]] = []
    for result in data.get("results", []):
        label_id = result.get("id")
        set_id = result.get("set_id")
        effective_time = result.get("effective_time")
        openfda_meta = result.get("openfda", {})

        generic_names = openfda_meta.get("generic_name", [])
        brand_names = openfda_meta.get("brand_name", [])

        # Use first generic/brand name
        generic = generic_names[0].strip() if generic_names else None
        brand = brand_names[0].strip() if brand_names else None

        eff_date = _parse_fda_date(effective_time)
        openfda_url = f'{settings.OPENFDA_API_BASE_URL}/drug/label.json?search=id:"{label_id}"' if label_id else None

        results.append({
            "application_number": set_id,
            "brand_name": brand,
            "generic_name": generic,
            "manufacturer_name": None,
            "product_type": "LABEL_UPDATE",
            "submission_type": None,
            "submission_status": None,
            "approval_date": eff_date,
            "openfda_url": openfda_url,
        })

    return results


async def fetch_openfda_data(db: AsyncSession) -> OpenfdaPollResult:
    """
    Poll openFDA for biosimilar approvals, label updates, and competitor filings.
    Upsert into DB and return a summary result.
    """
    svc = OpenfdaService()
    today = datetime.now(UTC).date()
    all_entries_data: list[dict[str, Any]] = []
    status = "success"
    error_message: str | None = None
    query_params: dict[str, Any] = {}

    try:
        # Query 1: Biosimilar approvals for nivolumab / ipilimumab
        q1_url = (
            f"{settings.OPENFDA_API_BASE_URL}/drug/drugsfda.json"
            f'?search=products.biosimilar:"Y"+AND+(openfda.generic_name:"nivolumab"+OR+openfda.generic_name:"ipilimumab")&limit=100'
        )
        logger.info("openFDA Query 1: biosimilar approvals", url=q1_url)
        q1_data = await svc._fetch_with_retry(q1_url)
        if "error" in q1_data:
            logger.info("openFDA Q1 no matches", error=q1_data.get("error", {}).get("message"))
        else:
            all_entries_data.extend(_extract_drugsfda_entries(q1_data, q1_url))

        # Query 2: Label updates for reference products
        q2_url = (
            f'{settings.OPENFDA_API_BASE_URL}/drug/label.json'
            f'?search=openfda.generic_name:"nivolumab"+OR+openfda.generic_name:"ipilimumab"&limit=100'
        )
        logger.info("openFDA Query 2: label updates", url=q2_url)
        q2_data = await svc._fetch_with_retry(q2_url)
        if "error" in q2_data:
            logger.info("openFDA Q2 no matches", error=q2_data.get("error", {}).get("message"))
        else:
            all_entries_data.extend(_extract_label_entries(q2_data, q2_url))

        # Query 3: Competitor-specific brand names
        q3_url = (
            f'{settings.OPENFDA_API_BASE_URL}/drug/drugsfda.json'
            f'?search=openfda.brand_name:"ABP+206"+OR+openfda.brand_name:"JPB898"+OR+openfda.brand_name:"Xdivane"+OR+openfda.brand_name:"HLX18"&limit=100'
        )
        logger.info("openFDA Query 3: competitor product codes", url=q3_url)
        q3_data = await svc._fetch_with_retry(q3_url)
        if "error" in q3_data:
            logger.info("openFDA Q3 no matches", error=q3_data.get("error", {}).get("message"))
        else:
            all_entries_data.extend(_extract_drugsfda_entries(q3_data, q3_url))

        query_params = {
            "q1": q1_url,
            "q2": q2_url,
            "q3": q3_url,
        }

    except httpx.HTTPStatusError as exc:
        logger.error("openFDA HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        error_message = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    except Exception as exc:
        logger.error("openFDA fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()

    # Serialize entries for JSON storage
    serialized_entries: list[dict[str, Any]] = []
    for entry in all_entries_data:
        ser = dict(entry)
        if isinstance(ser.get("approval_date"), date):
            ser["approval_date"] = ser["approval_date"].isoformat()
        serialized_entries.append(ser)

    # Upsert raw poll keyed by poll_date
    poll_result = await db.execute(
        select(OpenfdaRawPoll).where(OpenfdaRawPoll.poll_date == today)
    )
    existing_poll = poll_result.scalar_one_or_none()

    if existing_poll:
        existing_poll.raw_json = {"entries": serialized_entries}  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        existing_poll.endpoint_url = settings.OPENFDA_API_BASE_URL  # type: ignore[assignment]
        existing_poll.query_params = query_params  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = OpenfdaRawPoll(
            poll_date=today,
            endpoint_url=settings.OPENFDA_API_BASE_URL,
            query_params=query_params,
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

    # Upsert entries deduped by (application_number, approval_date) or (brand_name, approval_date)
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_entries_data:
        app_num = entry_data.get("application_number")
        brand = entry_data.get("brand_name")
        approval_date = entry_data.get("approval_date")
        product_type = entry_data.get("product_type")

        molecule = _match_molecule(entry_data.get("generic_name"), molecules)
        competitor = _match_competitor(entry_data.get("manufacturer_name"), competitors)
        is_relevant = (
            molecule is not None
            or competitor is not None
            or _brand_matches_known_code(brand)
        )

        # Build dedup query
        existing_stmt = select(OpenfdaEntry).where(
            OpenfdaEntry.raw_poll_id == raw_poll.id,
        )
        if app_num:
            existing_stmt = existing_stmt.where(OpenfdaEntry.application_number == app_num)
        else:
            existing_stmt = existing_stmt.where(OpenfdaEntry.application_number.is_(None))

        if product_type == "LABEL_UPDATE":
            # For labels, dedupe by brand_name + approval_date
            if brand:
                existing_stmt = existing_stmt.where(OpenfdaEntry.brand_name == brand)
            else:
                existing_stmt = existing_stmt.where(OpenfdaEntry.brand_name.is_(None))
        else:
            # For drugsfda, dedupe by application_number + approval_date
            pass  # application_number already in filter

        if approval_date:
            existing_stmt = existing_stmt.where(OpenfdaEntry.approval_date == approval_date)
        else:
            existing_stmt = existing_stmt.where(OpenfdaEntry.approval_date.is_(None))

        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.submission_status = entry_data.get("submission_status")  # type: ignore[assignment]
            existing_entry.openfda_url = entry_data.get("openfda_url")  # type: ignore[assignment]
            existing_entry.molecule_id = molecule.id if molecule else None  # type: ignore[assignment]
            existing_entry.competitor_id = competitor.id if competitor else None  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
            existing_entry.product_type = product_type  # type: ignore[assignment]
            existing_entry.submission_type = entry_data.get("submission_type")  # type: ignore[assignment]
            existing_entry.generic_name = entry_data.get("generic_name")  # type: ignore[assignment]
            existing_entry.brand_name = brand  # type: ignore[assignment]
            existing_entry.manufacturer_name = entry_data.get("manufacturer_name")  # type: ignore[assignment]
            existing_entry.approval_date = approval_date  # type: ignore[assignment]
        else:
            db_entry = OpenfdaEntry(
                raw_poll_id=raw_poll.id,
                application_number=app_num,
                brand_name=brand,
                generic_name=entry_data.get("generic_name"),
                manufacturer_name=entry_data.get("manufacturer_name"),
                product_type=product_type,
                submission_type=entry_data.get("submission_type"),
                submission_status=entry_data.get("submission_status"),
                approval_date=approval_date,
                openfda_url=entry_data.get("openfda_url"),
                molecule_id=molecule.id if molecule else None,
                competitor_id=competitor.id if competitor else None,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return OpenfdaPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_date=today,
        status=status,
        new_entries=new_entries,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_openfda_entries(
    raw_poll_id: uuid.UUID, db: AsyncSession
) -> int:
    """
    For every new is_relevant=true entry in the given poll,
    create GeoSignals for all countries.
    """
    # Fetch all active countries (FDA signals are global)
    country_result = await db.execute(select(Country).where(Country.is_active.is_(True)))
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No active countries found; skipping signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(OpenfdaEntry).where(
            OpenfdaEntry.raw_poll_id == raw_poll_id,
            OpenfdaEntry.is_relevant.is_(True),
            OpenfdaEntry.signals_created_at.is_(None),
        )
    )
    entries = list(entry_result.scalars().all())

    signals_created = 0
    now = datetime.now(UTC)
    for entry in entries:
        # Skip if no molecule (GeoSignal requires molecule_id)
        if not entry.molecule_id:
            continue

        if entry.product_type == "BIOSIMILAR" or entry.submission_status == "AP":
            signal_type = SignalType.FDA_BIOSIMILAR_APPROVAL
            _title = f"FDA Approval: {entry.brand_name or entry.generic_name}"
            description = (
                f"{entry.manufacturer_name or 'Unknown sponsor'} received FDA approval for "
                f"{entry.brand_name or entry.generic_name}. "
                f"Application: {entry.application_number or 'N/A'}. "
                f"This triggers global filing cascades."
            )
            confidence = Confidence.CONFIRMED
            tier = 1
            relevance_score = 95
            _tags = ["regulatory", "fda", "approval", "biosimilar", "global"]
            department_tags = ["commercial", "medical", "regulatory", "market_access"]
        elif entry.product_type == "LABEL_UPDATE":
            signal_type = SignalType.FDA_LABEL_UPDATE
            _title = f"FDA Label Update: {entry.generic_name}"
            description = (
                f"New FDA label issued for {entry.generic_name}. "
                f"Effective: {entry.approval_date or 'N/A'}. Review for indication changes."
            )
            confidence = Confidence.CONFIRMED
            tier = 3
            relevance_score = 80
            _tags = ["regulatory", "fda", "label", "medical"]
            department_tags = ["medical", "regulatory"]
        elif entry.submission_status == "TA":
            signal_type = SignalType.FDA_PENDING_APPROVAL
            _title = f"FDA Tentative Approval: {entry.brand_name or entry.generic_name}"
            description = (
                f"{entry.manufacturer_name or 'Unknown sponsor'} received FDA tentative approval for "
                f"{entry.brand_name or entry.generic_name}. "
                f"Application: {entry.application_number or 'N/A'}."
            )
            confidence = Confidence.PROBABLE
            tier = 2
            relevance_score = 85
            _tags = ["regulatory", "fda", "tentative_approval", "biosimilar"]
            department_tags = ["commercial", "medical", "regulatory", "market_access"]
        else:
            # Pending BLA or other status -> Tier 2
            signal_type = SignalType.FDA_PENDING_APPROVAL
            _title = f"FDA Pending Approval: {entry.brand_name or entry.generic_name}"
            description = (
                f"FDA submission pending for {entry.brand_name or entry.generic_name} "
                f"({entry.generic_name or 'unknown substance'}). "
                f"Status: {entry.submission_status or 'pending'}. "
                f"Application: {entry.application_number or 'N/A'}."
            )
            confidence = Confidence.PROBABLE
            tier = 2
            relevance_score = 85
            _tags = ["regulatory", "fda", "pending", "biosimilar"]
            department_tags = ["commercial", "medical", "regulatory", "market_access"]

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
                source_url=entry.openfda_url,
                source_type="openfda",
                tier=tier,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created openFDA GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
