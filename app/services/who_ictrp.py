from __future__ import annotations

import contextlib
import csv
import os
import re
import tempfile
import uuid
import zipfile
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
from app.models.who_ictrp import WhoIctrpEntry, WhoIctrpRawPoll
from app.schemas.who_ictrp import WhoIctrpPollResult

logger = get_logger(__name__)

_SEARCH_KEYWORDS = [
    "nivolumab", "opdivo", "ipilimumab", "yervoy",
    "abp 206", "jpb898", "xdivane", "hlx18", "ba1104", "mb11",
    "biosimilar", "biosimilarity",
]

_COMPETITOR_ALIAS_MAP: dict[str, str] = {
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


class WhoIctrpService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SEC_EDGAR_USER_AGENT or "Biosim/1.0 (intelligence@biosimintel.com)",
                "Accept": "text/csv, application/zip, text/html",
            },
            timeout=float(settings.WHO_ICTRP_DOWNLOAD_TIMEOUT),
            follow_redirects=True,
        )

    async def _fetch_text(self, url: str) -> str:
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text

    async def _download_to_file(self, url: str, dest_path: str) -> None:
        """Stream download to a temp file to avoid loading large CSVs into memory."""
        async with self.client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    async def close(self) -> None:
        await self.client.aclose()


def _discover_download_url(html: str) -> str | None:
    """Scrape the WHO ICTRP page for a .csv or .zip download link."""
    for pattern in (
        r'href="([^"]+\.csv)"',
        r'href="([^"]+\.zip)"',
    ):
        matches: list[str] = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            href = match.strip()
            if href.startswith("http"):
                return href
            if href.startswith("//"):
                return f"https:{href}"
            if href.startswith("/"):
                return f"https://www.who.int{href}"
    return None


def _extract_csv_from_zip(zip_path: str) -> str | None:
    """Extract the first .csv file from a ZIP archive to a temp path."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            return None
        extract_dir = os.path.dirname(zip_path)
        zf.extract(csv_names[0], extract_dir)
        return os.path.join(extract_dir, csv_names[0])


def _parse_ictrp_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _row_matches(row: dict[str, str]) -> bool:
    searchable = " ".join([
        row.get("Public_title", ""),
        row.get("Scientific_title", ""),
        row.get("Intervention", ""),
        row.get("Condition", ""),
    ]).lower()
    return any(kw.lower() in searchable for kw in _SEARCH_KEYWORDS)


def _is_valid_csv_file(path: str) -> bool:
    """Quick validation that the file looks like an ICTRP CSV."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
            if "TrialID" in sample or "Public_title" in sample:
                return True
            first_line = sample.splitlines()[0] if sample else ""
            return first_line.count(",") >= 5
    except OSError:
        return False


async def fetch_who_ictrp_data(db: AsyncSession) -> WhoIctrpPollResult:
    """
    Download WHO ICTRP bulk CSV, filter for relevant trials,
    upsert into DB, and return a summary result.
    """
    svc = WhoIctrpService()
    poll_month = datetime.now(UTC).strftime("%Y-%m")
    status = "success"
    error_message: str | None = None
    total_rows = 0
    filtered_rows = 0
    all_parsed_entries: list[dict[str, Any]] = []
    download_url = ""
    csv_filename: str | None = None

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
    for comp in competitors:
        cid: uuid.UUID = cast(uuid.UUID, comp.id)
        if comp.canonical_name:
            competitor_keywords[comp.canonical_name.lower().strip()] = cid
        if comp.parent_company:
            competitor_keywords[comp.parent_company.lower().strip()] = cid
        if comp.asset_code:
            competitor_keywords[comp.asset_code.lower().strip()] = cid

    for alias, target_name in _COMPETITOR_ALIAS_MAP.items():
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

    temp_csv_path: str | None = None
    try:
        # Step 1: Discover download URL
        discovered: str | None = None
        for page_url in (
            "https://www.who.int/clinical-trials-registry-platform/data-sets",
            "https://www.who.int/tools/clinical-trials-registry-platform/network/who-data-set/archived",
            settings.WHO_ICTRP_BASE_URL,
        ):
            try:
                logger.info("Fetching WHO ICTRP page for download links", url=page_url)
                html = await svc._fetch_text(page_url)
                discovered = _discover_download_url(html)
                if discovered:
                    break
            except httpx.HTTPStatusError:
                logger.warning("WHO ICTRP page fetch failed", url=page_url)
                continue

        download_url = discovered or f"{settings.WHO_ICTRP_BASE_URL}/download?download=1"
        logger.info("WHO ICTRP download URL", url=download_url)

        # Step 2: Stream download to temp file
        suffix = ".zip" if ".zip" in download_url.lower() else ".csv"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        await svc._download_to_file(download_url, temp_path)

        if suffix == ".zip":
            extracted = _extract_csv_from_zip(temp_path)
            os.remove(temp_path)
            if not extracted:
                raise ValueError("ZIP downloaded but no CSV found inside")
            temp_csv_path = extracted
            csv_filename = os.path.basename(extracted)
        else:
            temp_csv_path = temp_path
            csv_filename = os.path.basename(temp_path)

        if not _is_valid_csv_file(temp_csv_path):
            raise ValueError(f"Downloaded file does not appear to be a valid ICTRP CSV: {download_url}")

        # Step 3: Parse CSV with DictReader (memory-efficient, row-by-row)
        with open(temp_csv_path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                if _row_matches(row):
                    filtered_rows += 1
                    all_parsed_entries.append({
                        "trial_id": row.get("TrialID", "").strip(),
                        "reg_id": row.get("RegID", "").strip() or None,
                        "public_title": row.get("Public_title", "").strip(),
                        "scientific_title": row.get("Scientific_title", "").strip() or None,
                        "intervention": row.get("Intervention", "").strip() or None,
                        "condition": row.get("Condition", "").strip() or None,
                        "recruitment_status": row.get("Recruitment_status", "").strip() or None,
                        "phase": row.get("Phase", "").strip() or None,
                        "study_type": row.get("Study_type", "").strip() or None,
                        "date_registration": _parse_ictrp_date(row.get("Date_registration")),
                        "date_enrolment": _parse_ictrp_date(row.get("Date_enrolment")),
                        "countries": row.get("Countries", "").strip() or None,
                        "source_register": row.get("Source_register", "").strip() or None,
                        "url": row.get("Url", "").strip() or None,
                    })

    except httpx.HTTPStatusError as exc:
        logger.error("WHO ICTRP HTTP error", status_code=exc.response.status_code, url=str(exc.request.url))
        status = "failed"
        # For streamed downloads, response.text may not be available
        try:
            body = exc.response.text[:500]
        except Exception:
            body = exc.response.reason_phrase
        error_message = f"HTTP {exc.response.status_code}: {body}"
    except Exception as exc:
        logger.error("WHO ICTRP fetch error", error=str(exc))
        status = "failed"
        error_message = str(exc)[:1000]
    finally:
        await svc.close()
        if temp_csv_path and os.path.exists(temp_csv_path):
            with contextlib.suppress(OSError):
                os.remove(temp_csv_path)

    # Upsert raw poll keyed by poll_month
    poll_result = await db.execute(
        select(WhoIctrpRawPoll).where(WhoIctrpRawPoll.poll_month == poll_month)
    )
    existing_poll = poll_result.scalar_one_or_none()

    if existing_poll:
        existing_poll.download_url = download_url  # type: ignore[assignment]
        existing_poll.csv_filename = csv_filename  # type: ignore[assignment]
        existing_poll.total_rows = total_rows  # type: ignore[assignment]
        existing_poll.filtered_rows = filtered_rows  # type: ignore[assignment]
        existing_poll.status = status  # type: ignore[assignment]
        existing_poll.error_message = error_message  # type: ignore[assignment]
        raw_poll = existing_poll
    else:
        raw_poll = WhoIctrpRawPoll(
            poll_month=poll_month,
            download_url=download_url,
            csv_filename=csv_filename,
            total_rows=total_rows,
            filtered_rows=filtered_rows,
            status=status,
            error_message=error_message,
        )
        db.add(raw_poll)

    await db.commit()
    await db.refresh(raw_poll)

    # Upsert entries deduped by trial_id
    new_entries = 0
    relevant_entries = 0
    for entry_data in all_parsed_entries:
        trial_id = entry_data["trial_id"]
        public_title = entry_data["public_title"]
        if not trial_id or not public_title:
            continue

        combined = " ".join([
            public_title.lower(),
            (entry_data.get("scientific_title") or "").lower(),
            (entry_data.get("intervention") or "").lower(),
            (entry_data.get("condition") or "").lower(),
        ])

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

        is_relevant = (molecule_id is not None) or (competitor_id is not None)

        # Check for existing entry (dedup globally by trial_id)
        existing_stmt = select(WhoIctrpEntry).where(
            WhoIctrpEntry.trial_id == trial_id,
        )
        existing_result = await db.execute(existing_stmt)
        existing_entry = existing_result.scalar_one_or_none()

        if existing_entry:
            existing_entry.public_title = public_title
            existing_entry.scientific_title = entry_data.get("scientific_title")  # type: ignore[assignment]
            existing_entry.intervention = entry_data.get("intervention")  # type: ignore[assignment]
            existing_entry.condition = entry_data.get("condition")  # type: ignore[assignment]
            existing_entry.recruitment_status = entry_data.get("recruitment_status")  # type: ignore[assignment]
            existing_entry.phase = entry_data.get("phase")  # type: ignore[assignment]
            existing_entry.study_type = entry_data.get("study_type")  # type: ignore[assignment]
            existing_entry.date_registration = entry_data.get("date_registration")  # type: ignore[assignment]
            existing_entry.date_enrolment = entry_data.get("date_enrolment")  # type: ignore[assignment]
            existing_entry.countries = entry_data.get("countries")  # type: ignore[assignment]
            existing_entry.source_register = entry_data.get("source_register")  # type: ignore[assignment]
            existing_entry.url = entry_data.get("url")  # type: ignore[assignment]
            existing_entry.molecule_id = molecule_id  # type: ignore[assignment]
            existing_entry.competitor_id = competitor_id  # type: ignore[assignment]
            existing_entry.is_relevant = is_relevant  # type: ignore[assignment]
        else:
            db_entry = WhoIctrpEntry(
                raw_poll_id=raw_poll.id,
                trial_id=trial_id,
                reg_id=entry_data.get("reg_id"),
                public_title=public_title,
                scientific_title=entry_data.get("scientific_title"),
                intervention=entry_data.get("intervention"),
                condition=entry_data.get("condition"),
                recruitment_status=entry_data.get("recruitment_status"),
                phase=entry_data.get("phase"),
                study_type=entry_data.get("study_type"),
                date_registration=entry_data.get("date_registration"),
                date_enrolment=entry_data.get("date_enrolment"),
                countries=entry_data.get("countries"),
                source_register=entry_data.get("source_register"),
                url=entry_data.get("url"),
                molecule_id=molecule_id,
                competitor_id=competitor_id,
                is_relevant=is_relevant,
            )
            db.add(db_entry)
            new_entries += 1
            if is_relevant:
                relevant_entries += 1

    await db.commit()

    return WhoIctrpPollResult(
        poll_id=raw_poll.id,  # type: ignore[arg-type]
        poll_month=poll_month,
        status=status,
        total_rows=total_rows,
        filtered_rows=filtered_rows,
        relevant_entries=relevant_entries,
        signals_created=0,
    )


async def create_signals_from_ictrp_entries(
    raw_poll_id: uuid.UUID, db: AsyncSession
) -> int:
    """
    For every new is_relevant=true entry in the given poll,
    create GeoSignals for all active countries.
    ChiCTR/CTRI → tier 2; others → tier 3.
    """
    # Fetch all active countries
    country_result = await db.execute(select(Country).where(Country.is_active.is_(True)))
    countries = list(country_result.scalars().all())
    if not countries:
        logger.warning("No active countries found; skipping ICTRP signal creation")
        return 0

    # Fetch relevant entries for this poll that haven't had signals created yet
    entry_result = await db.execute(
        select(WhoIctrpEntry).where(
            WhoIctrpEntry.raw_poll_id == raw_poll_id,
            WhoIctrpEntry.is_relevant.is_(True),
            WhoIctrpEntry.signals_created_at.is_(None),
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

        source_reg = (entry.source_register or "").upper()
        if source_reg in ("CHICTR", "CTRI"):
            tier = 2
            relevance_score = 80
            confidence = Confidence.PROBABLE
            department_tags = ["commercial", "medical", "regulatory"]
        else:
            tier = 3
            relevance_score = 75
            confidence = Confidence.PROBABLE
            department_tags = ["medical", "commercial"]

        description = (
            f"New trial registered in {entry.source_register or 'Unknown'} "
            f"({entry.countries or 'N/A'}). Phase: {entry.phase or 'N/A'}. "
            f"Status: {entry.recruitment_status or 'N/A'}. "
            f"Molecule: {mol_name or 'Unknown'}. "
            f"Competitor: {comp_name or 'Unknown'}. "
            f"This signals emerging market activity."
        )

        for country in countries:
            signal = GeoSignal(
                molecule_id=entry.molecule_id,
                competitor_id=entry.competitor_id,
                region_id=country.region_id,
                country_ids=[country.id],
                signal_type=SignalType.TRIAL_UPDATE,
                confidence=confidence,
                relevance_score=relevance_score,
                department_tags=department_tags,
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=description,
                source_url=entry.url or "https://www.who.int/clinical-trials-registry-platform",
                source_type="who_ictrp",
                tier=tier,
            )
            db.add(signal)
            signals_created += 1

        entry.signals_created_at = now  # type: ignore[assignment]

    await db.commit()
    logger.info("Created WHO ICTRP GeoSignals", count=signals_created, poll_id=str(raw_poll_id))
    return signals_created
