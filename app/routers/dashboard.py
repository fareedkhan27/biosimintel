from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.combo import CompetitorMoleculeAssignment
from app.models.competitor import Competitor
from app.models.ema_epar import EmaEparEntry, EmaEparRawPoll
from app.models.event import Event
from app.models.geo import CompetitorCapability, Country, Region
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal
from app.models.openfda import OpenfdaEntry, OpenfdaRawPoll
from app.models.press_release import PressReleaseRaw
from app.models.pubmed import PubmedEntry, PubmedRawPoll
from app.models.signal import GeoSignal
from app.models.social_media import SocialMediaRaw
from app.schemas.dashboard import (
    CompetitorDashboard,
    DashboardSummary,
    HeatmapCountry,
    RegionDashboard,
    SourceHealth,
    TimelineSignal,
)

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory="app/templates")

_WATCH_LIST_NAMES = {"zydus", "boan", "enzene", "henlius"}

_SOURCES: dict[str, str] = {
    "clinicaltrials": "ACTIVE",
    "ema_epar": "ACTIVE",
    "openfda": "ACTIVE",
    "pubmed": "ACTIVE",
    "press_release": "ACTIVE",
    "social_media": "ACTIVE",
    "uspto": "DORMANT",
    "epo": "DORMANT",
    "who_ictpr": "DORMANT",
    "eu_ctis": "DORMANT",
}

# Geo-threat scoring constants (mirrors app/services/threat_service.py)
_STAGE_40_KEYWORDS = ("phase 3", "bla", "prep", "approved", "filing", "launched", "phase_3")
_STAGE_15_KEYWORDS = ("phase 1", "phase 2", "ind", "phase_1", "phase_2", "phase_1_2")
_STAGE_5_KEYWORDS = ("preclinical", "undisclosed", "pipeline", "pre_clinical", "watch", "terminated")


def _score_stage(stage: str | None) -> int:
    if not stage:
        return 5
    lower = stage.lower()
    if any(k in lower for k in _STAGE_40_KEYWORDS):
        return 40
    if any(k in lower for k in _STAGE_15_KEYWORDS):
        return 15
    if any(k in lower for k in _STAGE_5_KEYWORDS):
        return 5
    return 5


def _combo_bonus(capability: str | None) -> int:
    if capability == "FULL":
        return 10
    if capability == "PARTIAL":
        return 5
    return 0


def _apply_multiplier(raw_score: float, operating_model: Any) -> float:
    if operating_model and operating_model.value == "OPM":
        return raw_score * 1.2
    if operating_model and operating_model.value == "Passive":
        return raw_score * 0.5
    return raw_score


def _calc_relevance_score(
    country: Country,
    competitor_stage: str | None,
    capability: Any | None,
    combo_capability: str | None,
) -> int:
    base_score = _score_stage(competitor_stage)
    geo_bonus = 0
    if capability:
        has_any = capability.has_local_regulatory_filing or capability.has_local_commercial_infrastructure
        if has_any:
            if capability.has_local_commercial_infrastructure:
                geo_bonus += 25
            if capability.has_local_regulatory_filing:
                geo_bonus += 15
            if capability.has_local_manufacturing:
                geo_bonus += 10
    combo = _combo_bonus(combo_capability)
    raw_score = base_score + geo_bonus + combo
    multiplied = _apply_multiplier(float(raw_score), country.operating_model)
    return min(int(multiplied), 100)


async def _get_target_molecule_ids(db: AsyncSession) -> list[UUID]:
    result = await db.execute(
        select(Molecule.id).where(Molecule.molecule_name.in_(["nivolumab", "ipilimumab"]))
    )
    return [row[0] for row in result.all()]


def _threat_level(score: int, has_signals: bool = True) -> str:
    if not has_signals or score == 0:
        return "MONITORING"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "MONITORING"


def _is_watch_list(name: str) -> bool:
    lower = name.lower()
    return any(watch in lower for watch in _WATCH_LIST_NAMES)


def _signal_title(gs: GeoSignal, event: Event | None, competitor_name: str) -> str:
    if event and event.summary:
        summary = cast(str, event.summary)
        title = summary.strip()
        if len(title) > 120:
            title = title[:117] + "..."
        return title
    if gs.delta_note:
        delta = cast(str, gs.delta_note)
        note = delta.strip()
        if len(note) > 120:
            note = note[:117] + "..."
        return note
    signal_label = gs.signal_type.value.replace("_", " ").title()
    return f"{signal_label} — {competitor_name or 'Unknown'}"


@router.get("/heatmap", response_model=list[HeatmapCountry])
async def get_heatmap(
    region: str | None = Query(None),
    country_code: str | None = Query(None),
    operating_model: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[HeatmapCountry]:
    cutoff_30d = datetime.now(UTC) - timedelta(days=30)
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)

    target_molecule_ids = await _get_target_molecule_ids(db)

    # A. Build country query
    stmt = select(Country).options(selectinload(Country.region)).where(Country.is_active.is_(True))
    if region and region != "all":
        if region == "Russia":
            stmt = stmt.where(Country.code == "RU")
        else:
            reg = await db.scalar(select(Region).where(Region.code == region.upper()))
            if reg:
                stmt = stmt.where(Country.region_id == reg.id)
    if country_code:
        stmt = stmt.where(Country.code == country_code.upper())
    if operating_model and operating_model != "all":
        _model_normalized = operating_model.upper() if operating_model.upper() in ("LPM", "OPM") else operating_model.title()
        stmt = stmt.where(Country.operating_model == _model_normalized)

    countries_result = await db.execute(stmt.order_by(Country.code))
    countries = list(countries_result.scalars().all())

    if not countries:
        return []

    country_ids = [cast(UUID, c.id) for c in countries]

    # B. Signal counts per country (last 30d, nivolumab/ipilimumab only)
    # Use unnest to expand country_ids array into per-country rows
    subq = (
        select(func.unnest(GeoSignal.country_ids).label("cid"), GeoSignal.id)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_30d)
        .subquery()
    )
    signals_result = await db.execute(
        select(subq.c.cid, func.count(subq.c.id))
        .where(subq.c.cid.in_(country_ids))
        .group_by(subq.c.cid)
    )
    signals_by_country: dict[UUID, int] = {row[0]: row[1] for row in signals_result.all()}

    # Signal counts 7d per country
    subq_7d = (
        select(func.unnest(GeoSignal.country_ids).label("cid"), GeoSignal.id)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_7d)
        .subquery()
    )
    signals_7d_result = await db.execute(
        select(subq_7d.c.cid, func.count(subq_7d.c.id))
        .where(subq_7d.c.cid.in_(country_ids))
        .group_by(subq_7d.c.cid)
    )
    signals_7d_by_country: dict[UUID, int] = {row[0]: row[1] for row in signals_7d_result.all()}

    # C. Pre-load competitor assignments for target molecules
    assignments_result = await db.execute(
        select(CompetitorMoleculeAssignment, Competitor)
        .join(Competitor, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
        .where(CompetitorMoleculeAssignment.molecule_id.in_(target_molecule_ids))
    )
    assign_rows = [(a, c) for a, c in assignments_result.all()]
    comp_ids = list({a.competitor_id for a, _ in assign_rows})

    comp_stages: dict[UUID, str | None] = {}
    comp_combos: dict[UUID, str | None] = {}
    for a, c in assign_rows:
        cid = a.competitor_id
        stage = a.development_stage or c.development_stage
        if cid not in comp_stages or _score_stage(stage) > _score_stage(comp_stages[cid]):
            comp_stages[cid] = stage
        if cid not in comp_combos:
            comp_combos[cid] = a.combo_capability.value if a.combo_capability else None

    # D. Pre-load capabilities for regions of filtered countries
    region_ids = list({cast(UUID, c.region_id) for c in countries if c.region_id})
    cap_result = await db.execute(
        select(CompetitorCapability)
        .where(CompetitorCapability.competitor_id.in_(comp_ids))
        .where(CompetitorCapability.region_id.in_(region_ids))
    )
    caps_by_region_comp: dict[tuple[UUID, UUID], Any] = {}
    for capability in cap_result.scalars().all():
        caps_by_region_comp[(cast(UUID, capability.competitor_id), cast(UUID, capability.region_id))] = capability

    # E. Pre-load top competitor by signal count per country
    # Signals with competitor in last 30d
    comp_signals_result = await db.execute(
        select(GeoSignal.country_ids, Competitor.id, Competitor.canonical_name)
        .join(Competitor, GeoSignal.competitor_id == Competitor.id)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_30d)
    )
    comp_signals_by_country: dict[UUID, dict[str, int]] = {}
    for cids, _comp_id, comp_name in comp_signals_result.all():
        if cids:
            for cid in cids:
                if cid in country_ids:
                    comp_signals_by_country.setdefault(cid, {})
                    comp_signals_by_country[cid][comp_name] = comp_signals_by_country[cid].get(comp_name, 0) + 1

    # F. Build response per country
    result: list[HeatmapCountry] = []
    for country in countries:
        cid = cast(UUID, country.id)
        signal_count_30d = signals_by_country.get(cid, 0)
        signal_count_7d = signals_7d_by_country.get(cid, 0)
        has_signals = signal_count_30d > 0

        # Compute threat score for THIS country from live capability data
        max_threat = 0
        best_comp_id: UUID | None = None
        for comp_id in comp_ids:
            cap = caps_by_region_comp.get((comp_id, cast(UUID, country.region_id)))
            score = _calc_relevance_score(
                country, comp_stages.get(comp_id), cap, comp_combos.get(comp_id)
            )
            if score > max_threat:
                max_threat = score
                best_comp_id = comp_id

        # Top competitor: highest capability score, tie-broken by signal count in this country
        top_comp = "Monitoring"
        if has_signals and best_comp_id:
            # Tie-break by signal count
            comp_sig_counts = comp_signals_by_country.get(cid, {})
            best_count = comp_sig_counts.get(
                next((c.canonical_name for a, c in assign_rows if a.competitor_id == best_comp_id), ""), 0
            )
            for comp_id in comp_ids:
                cap = caps_by_region_comp.get((comp_id, cast(UUID, country.region_id)))
                score = _calc_relevance_score(
                    country, comp_stages.get(comp_id), cap, comp_combos.get(comp_id)
                )
                if score == max_threat:
                    comp_name = next((c.canonical_name for a, c in assign_rows if a.competitor_id == comp_id), "")
                    count = comp_sig_counts.get(comp_name, 0)
                    if count > best_count:
                        best_comp_id = comp_id
                        best_count = count

            for a, c in assign_rows:
                if a.competitor_id == best_comp_id:
                    top_comp = c.canonical_name
                    break

        result.append(
            HeatmapCountry(
                country_code=cast(str, country.code),
                country_name=cast(str, country.name),
                region=cast(str, country.region.code.value) if country.region and country.region.code else "",
                highest_competitor_threat_score=max_threat,
                threat_level=cast(Any, _threat_level(max_threat, has_signals)),
                top_competitor_name=top_comp if has_signals else "Monitoring",
                signal_count_7d=signal_count_7d,
                signal_count_30d=signal_count_30d,
            )
        )
    return result


@router.get("/timeline", response_model=list[TimelineSignal])
async def get_timeline(
    region: str | None = Query(None),
    tier: int | None = Query(None, ge=1, le=3),
    source: str | None = Query(None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=500),
    country_id: UUID | None = Query(None),
    operating_model: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[TimelineSignal]:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    target_molecule_ids = await _get_target_molecule_ids(db)

    stmt = (
        select(GeoSignal, Event, Competitor)
        .join(Event, GeoSignal.event_id == Event.id, isouter=True)
        .join(Competitor, GeoSignal.competitor_id == Competitor.id, isouter=True)
        .where(GeoSignal.created_at >= cutoff)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
    )

    if tier is not None:
        stmt = stmt.where(GeoSignal.tier == tier)
    if source:
        stmt = stmt.where(GeoSignal.source_type == source)

    if region:
        if region == "Russia":
            russia_result = await db.execute(
                select(Country.id).where(Country.code == "RU")
            )
            russia_id = russia_result.scalar_one_or_none()
            if russia_id:
                stmt = stmt.where(GeoSignal.country_ids.contains([russia_id]))
            else:
                return []
        else:
            region_result = await db.execute(
                select(Region).where(Region.code == region.upper())
            )
            region_obj = region_result.scalar_one_or_none()
            if region_obj:
                country_result = await db.execute(
                    select(Country.id).where(Country.region_id == region_obj.id)
                )
                region_country_ids = [row[0] for row in country_result.all()]
                if region_country_ids:
                    stmt = stmt.where(GeoSignal.country_ids.overlap(region_country_ids))
                else:
                    return []
            else:
                return []

    if country_id:
        stmt = stmt.where(GeoSignal.country_ids.contains([country_id]))

    if operating_model:
        _model_normalized = operating_model.upper() if operating_model.upper() in ("LPM", "OPM") else operating_model.title()
        model_country_result = await db.execute(
            select(Country.id).where(Country.operating_model == _model_normalized)
        )
        model_country_ids = [row[0] for row in model_country_result.all()]
        if model_country_ids:
            stmt = stmt.where(GeoSignal.country_ids.overlap(model_country_ids))
        else:
            return []

    stmt = stmt.order_by(GeoSignal.created_at.desc()).limit(limit)
    signals_result = await db.execute(stmt)
    signals = signals_result.all()

    all_country_ids: set[UUID] = set()
    for gs, _, _ in signals:
        if gs.country_ids:
            all_country_ids.update(gs.country_ids)

    country_meta: dict[UUID, dict[str, str]] = {}
    if all_country_ids:
        country_result = await db.execute(
            select(Country, Region.code)
            .join(Region, Country.region_id == Region.id)
            .where(Country.id.in_(all_country_ids))
        )
        for c, region_code in country_result.all():
            cid = cast(UUID, c.id)
            country_meta[cid] = {
                "name": cast(str, c.name) or "",
                "code": cast(str, c.code),
                "region": cast(str, region_code.value) if hasattr(region_code, "value") else str(region_code),
                "model": cast(str, c.operating_model.value) if c.operating_model else "",
            }

    # Group signals by fingerprint to deduplicate multi-country entries
    groups: dict[str, dict[str, Any]] = {}
    for gs, event, competitor in signals:
        comp_name = competitor.canonical_name if competitor else "Unknown"
        title = _signal_title(gs, event, comp_name)

        # Fingerprint: title + source_url + date + competitor_id + molecule_id
        date_key = gs.created_at.strftime("%Y-%m-%d") if gs.created_at else ""
        fp = f"{title}|{gs.source_url or ''}|{date_key}|{gs.competitor_id or ''!s}|{gs.molecule_id or ''!s}"

        if fp not in groups:
            groups[fp] = {
                "title": title,
                "tier": gs.tier,
                "source_type": gs.source_type,
                "competitor_name": comp_name,
                "created_at": gs.created_at,
                "url": gs.source_url,
                "event_date": event.event_date if event else None,
                "country_codes": set(),
            }
        if gs.country_ids:
            for cid in gs.country_ids:
                meta = country_meta.get(cid)
                if meta:
                    groups[fp]["country_codes"].add(meta["code"])

    result: list[TimelineSignal] = []
    for fp, g in list(groups.items())[:limit]:
        codes = sorted(g["country_codes"])
        if len(codes) == 1:
            country_name = codes[0]
        elif len(codes) > 1:
            country_name = f"{codes[0]} +{len(codes) - 1} more"
        else:
            country_name = "Regional"

        result.append(
            TimelineSignal(
                id=fp,
                title=g["title"],
                tier=g["tier"],
                source_type=g["source_type"],
                country_name=country_name,
                country_count=len(codes),
                country_codes=codes,
                competitor_name=g["competitor_name"],
                created_at=g["created_at"],
                url=g["url"],
                event_date=g["event_date"],
            )
        )
    return result


@router.get("/competitors", response_model=list[CompetitorDashboard])
async def get_competitors(
    region: str | None = Query(None),
    operating_model: str | None = Query(None),
    country_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[CompetitorDashboard]:
    target_molecule_ids = await _get_target_molecule_ids(db)

    # A. Get filtered country IDs
    country_q = select(Country.id)
    if region and region != "all":
        if region == "Russia":
            country_q = country_q.where(Country.code == "RU")
        else:
            reg = await db.scalar(select(Region).where(Region.code == region.upper()))
            if reg:
                country_q = country_q.where(Country.region_id == reg.id)
    if operating_model and operating_model != "all":
        _model_normalized = operating_model.upper() if operating_model.upper() in ("LPM", "OPM") else operating_model.title()
        country_q = country_q.where(Country.operating_model == _model_normalized)

    filtered_country_rows = await db.execute(country_q)
    filtered_country_ids = {row[0] for row in filtered_country_rows.all()}

    if not filtered_country_ids:
        return []

    # B. Get competitors assigned to nivolumab/ipilimumab with capabilities in filtered countries
    competitors_result = await db.execute(
        select(Competitor)
        .join(CompetitorMoleculeAssignment, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
        .join(CompetitorCapability, CompetitorCapability.competitor_id == Competitor.id)
        .where(CompetitorMoleculeAssignment.molecule_id.in_(target_molecule_ids))
        .where(CompetitorCapability.region_id.in_(
            select(Country.region_id).where(Country.id.in_(filtered_country_ids))
        ))
        .order_by(Competitor.canonical_name)
        .distinct()
    )
    competitors = list(competitors_result.scalars().all())

    if not competitors:
        return []

    competitor_ids = [cast(UUID, c.id) for c in competitors]

    assignments_result = await db.execute(
        select(CompetitorMoleculeAssignment, Molecule)
        .join(Molecule, CompetitorMoleculeAssignment.molecule_id == Molecule.id)
        .where(CompetitorMoleculeAssignment.competitor_id.in_(competitor_ids))
        .where(CompetitorMoleculeAssignment.molecule_id.in_(target_molecule_ids))
    )
    comp_molecules: dict[UUID, list[str]] = {cid: [] for cid in competitor_ids}
    for assignment, molecule in assignments_result.all():
        mol_name = cast(str, molecule.molecule_name)
        comp_id = cast(UUID, assignment.competitor_id)
        if mol_name not in comp_molecules[comp_id]:
            comp_molecules[comp_id].append(mol_name)

    signals_result = await db.execute(
        select(GeoSignal, Event)
        .join(Event, GeoSignal.event_id == Event.id, isouter=True)
        .where(GeoSignal.competitor_id.in_(competitor_ids))
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .order_by(GeoSignal.created_at.desc())
    )
    comp_signals: dict[UUID, list[tuple[GeoSignal, Event | None]]] = {
        cid: [] for cid in competitor_ids
    }
    comp_countries: dict[UUID, set[UUID]] = {cid: set() for cid in competitor_ids}
    for gs, event in signals_result.all():
        comp_id = cast(UUID, gs.competitor_id)
        # Only count signals/countries within the filtered set
        if gs.country_ids:
            filtered_cids = [cid for cid in gs.country_ids if cid in filtered_country_ids]
            if filtered_cids:
                comp_signals[comp_id].append((gs, event))
                for cid in filtered_cids:
                    comp_countries[comp_id].add(cid)

    all_active_country_ids: set[UUID] = set()
    for cid_set in comp_countries.values():
        all_active_country_ids.update(cid_set)
    country_code_map: dict[UUID, str] = {}
    if all_active_country_ids:
        cc_result = await db.execute(
            select(Country).where(Country.id.in_(all_active_country_ids))
        )
        for c in cc_result.scalars().all():
            country_code_map[cast(UUID, c.id)] = cast(str, c.code)

    result: list[CompetitorDashboard] = []
    for c in competitors:
        cid = cast(UUID, c.id)
        signals = comp_signals.get(cid, [])
        total = len(signals)
        latest_date = None
        latest_title = None
        if signals:
            latest_gs, latest_event = signals[0]
            latest_date = cast(datetime | None, latest_gs.created_at)
            latest_title = _signal_title(
                latest_gs, latest_event, cast(str, c.canonical_name)
            )

        molecules = comp_molecules.get(cid, [])

        comp_country_codes = sorted(
            {country_code_map.get(uid, "") for uid in comp_countries.get(cid, set())}
            - {""}
        )

        date_formatted = None
        if latest_date:
            date_formatted = latest_date.strftime("%b %Y - %H:%M")

        result.append(
            CompetitorDashboard(
                id=cid,
                name=cast(str, c.canonical_name),
                watch_list=_is_watch_list(cast(str, c.canonical_name)),
                molecules=molecules,
                active_countries_count=len(comp_countries.get(cid, set())),
                country_codes=comp_country_codes,
                latest_signal_date=latest_date,
                latest_signal_date_formatted=date_formatted,
                latest_signal_title=latest_title,
                total_signals_count=total,
            )
        )

    if country_id:
        result = [r for r in result if country_id in comp_countries.get(r.id, set())]

    return result


@router.get("/sources", response_model=list[SourceHealth])
async def get_sources(
    db: AsyncSession = Depends(get_db),
) -> list[SourceHealth]:
    target_molecule_ids = await _get_target_molecule_ids(db)

    result: list[SourceHealth] = []

    # ClinicalTrials.gov — use Event as proxy
    ct_poll = await db.execute(
        select(func.max(Event.created_at), func.count(Event.id))
        .where(Event.molecule_id.in_(target_molecule_ids))
    )
    ct_row = ct_poll.first()
    result.append(
        SourceHealth(
            source_name="clinicaltrials",
            status="ACTIVE",
            last_poll_timestamp=ct_row[0] if ct_row and ct_row[0] else None,
            signal_count_total=ct_row[1] if ct_row else 0,
            signal_count_7d=0,
        )
    )

    # EMA EPAR
    ema_poll = await db.execute(
        select(func.max(EmaEparRawPoll.poll_date), func.count(EmaEparEntry.id))
        .join(EmaEparEntry, EmaEparEntry.raw_poll_id == EmaEparRawPoll.id)
        .where(EmaEparEntry.molecule_id.in_(target_molecule_ids))
    )
    ema_row = ema_poll.first()
    result.append(
        SourceHealth(
            source_name="ema_epar",
            status="ACTIVE",
            last_poll_timestamp=ema_row[0] if ema_row and ema_row[0] else None,
            signal_count_total=ema_row[1] if ema_row else 0,
            signal_count_7d=0,
        )
    )

    # openFDA
    openfda_poll = await db.execute(
        select(func.max(OpenfdaRawPoll.poll_date), func.count(OpenfdaEntry.id))
        .join(OpenfdaEntry, OpenfdaEntry.raw_poll_id == OpenfdaRawPoll.id)
        .where(OpenfdaEntry.molecule_id.in_(target_molecule_ids))
    )
    openfda_row = openfda_poll.first()
    result.append(
        SourceHealth(
            source_name="openfda",
            status="ACTIVE",
            last_poll_timestamp=openfda_row[0] if openfda_row and openfda_row[0] else None,
            signal_count_total=openfda_row[1] if openfda_row else 0,
            signal_count_7d=0,
        )
    )

    # PubMed
    pubmed_poll = await db.execute(
        select(func.max(PubmedRawPoll.poll_date), func.count(PubmedEntry.id))
        .join(PubmedEntry, PubmedEntry.raw_poll_id == PubmedRawPoll.id)
        .where(PubmedEntry.molecule_id.in_(target_molecule_ids))
    )
    pubmed_row = pubmed_poll.first()
    result.append(
        SourceHealth(
            source_name="pubmed",
            status="ACTIVE",
            last_poll_timestamp=pubmed_row[0] if pubmed_row and pubmed_row[0] else None,
            signal_count_total=pubmed_row[1] if pubmed_row else 0,
            signal_count_7d=0,
        )
    )

    # Press Release
    press_poll = await db.execute(
        select(func.max(PressReleaseRaw.created_at), func.count(PressReleaseRaw.id))
        .where(PressReleaseRaw.molecule_id.in_(target_molecule_ids))
    )
    press_row = press_poll.first()
    result.append(
        SourceHealth(
            source_name="press_release",
            status="ACTIVE",
            last_poll_timestamp=press_row[0] if press_row and press_row[0] else None,
            signal_count_total=press_row[1] if press_row else 0,
            signal_count_7d=0,
        )
    )

    # Social Media
    social_poll = await db.execute(
        select(func.max(SocialMediaRaw.created_at), func.count(SocialMediaRaw.id))
        .where(SocialMediaRaw.molecule_id.in_(target_molecule_ids))
    )
    social_row = social_poll.first()
    result.append(
        SourceHealth(
            source_name="social_media",
            status="ACTIVE",
            last_poll_timestamp=social_row[0] if social_row and social_row[0] else None,
            signal_count_total=social_row[1] if social_row else 0,
            signal_count_7d=0,
        )
    )

    # Dormant sources
    for dormant in ["uspto", "epo", "who_ictpr", "eu_ctis"]:
        result.append(
            SourceHealth(
                source_name=dormant,
                status="DORMANT",
                last_poll_timestamp=None,
                signal_count_total=0,
                signal_count_7d=0,
            )
        )

    return result


@router.get("/regions", response_model=list[RegionDashboard])
async def get_regions(
    operating_model: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[RegionDashboard]:
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    cutoff_30d = datetime.now(UTC) - timedelta(days=30)

    target_molecule_ids = await _get_target_molecule_ids(db)

    regions_result = await db.execute(select(Region).order_by(Region.code))
    regions = list(regions_result.scalars().all())

    # Pre-load all scoring data
    assignments_result = await db.execute(
        select(CompetitorMoleculeAssignment, Competitor)
        .join(Competitor, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
        .where(CompetitorMoleculeAssignment.molecule_id.in_(target_molecule_ids))
    )
    assign_rows = [(a, c) for a, c in assignments_result.all()]
    comp_ids = list({a.competitor_id for a, _ in assign_rows})

    comp_stages: dict[UUID, str | None] = {}
    comp_combos: dict[UUID, str | None] = {}
    for a, c in assign_rows:
        cid = a.competitor_id
        stage = a.development_stage or c.development_stage
        if cid not in comp_stages or _score_stage(stage) > _score_stage(comp_stages[cid]):
            comp_stages[cid] = stage
        if cid not in comp_combos:
            comp_combos[cid] = a.combo_capability.value if a.combo_capability else None

    cap_result = await db.execute(
        select(CompetitorCapability)
        .where(CompetitorCapability.competitor_id.in_(comp_ids))
    )
    caps_by_region_comp: dict[tuple[UUID, UUID], Any] = {}
    for capability in cap_result.scalars().all():
        caps_by_region_comp[(cast(UUID, capability.competitor_id), cast(UUID, capability.region_id))] = capability

    # Per-country signals using unnest
    subq = (
        select(func.unnest(GeoSignal.country_ids).label("cid"), GeoSignal.id)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_30d)
        .subquery()
    )
    signals_result = await db.execute(
        select(subq.c.cid, func.count(subq.c.id))
        .group_by(subq.c.cid)
    )
    all_signals_by_country = {row[0]: row[1] for row in signals_result.all()}

    subq_7d = (
        select(func.unnest(GeoSignal.country_ids).label("cid"), GeoSignal.id)
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_7d)
        .subquery()
    )
    signals_7d_result = await db.execute(
        select(subq_7d.c.cid, func.count(subq_7d.c.id))
        .group_by(subq_7d.c.cid)
    )
    all_signals_7d_by_country = {row[0]: row[1] for row in signals_7d_result.all()}

    result: list[RegionDashboard] = []
    for region in regions:
        code = cast(str, region.code.value) if region.code else ""

        cq = select(Country).where(Country.region_id == region.id)
        if operating_model:
            _model_normalized = operating_model.upper() if operating_model.upper() in ("LPM", "OPM") else operating_model.title()
            cq = cq.where(Country.operating_model == _model_normalized)
        countries = (await db.execute(cq)).scalars().all()
        country_ids = [cast(UUID, c.id) for c in countries]

        if not countries:
            continue

        # Signal counts for this region's countries
        total_30d = sum(all_signals_by_country.get(cid, 0) for cid in country_ids)
        total_7d = sum(all_signals_7d_by_country.get(cid, 0) for cid in country_ids)

        # Per-country max threat using live capability data
        threat_scores = []
        for country in countries:
            max_score = 0
            for comp_id in comp_ids:
                cap = caps_by_region_comp.get((comp_id, cast(UUID, country.region_id)))
                score = _calc_relevance_score(
                    country, comp_stages.get(comp_id), cap, comp_combos.get(comp_id)
                )
                if score > max_score:
                    max_score = score
            threat_scores.append(max_score)

        avg_threat = round(sum(threat_scores) / len(threat_scores), 1) if threat_scores else 0.0

        # Top country = country with most signals in last 30d
        top_country = "N/A"
        top_country_signals = 0
        best_country_id: UUID | None = None
        if country_ids:
            best_country_id = max(country_ids, key=lambda cid: all_signals_by_country.get(cid, 0))
            top_country_obj = next(
                (c for c in countries if cast(UUID, c.id) == best_country_id), None
            )
            top_country = cast(str, top_country_obj.name) if top_country_obj else "N/A"
            top_country_signals = all_signals_by_country.get(best_country_id, 0)

        # Top competitor by signals in region
        competitor_signals: dict[str, int] = {}
        comp_signals_result = await db.execute(
            select(GeoSignal.country_ids, Competitor.canonical_name)
            .join(Competitor, GeoSignal.competitor_id == Competitor.id)
            .where(GeoSignal.molecule_id.in_(target_molecule_ids))
            .where(GeoSignal.created_at >= cutoff_30d)
        )
        for cids, comp_name in comp_signals_result.all():
            if cids:
                for cid in cids:
                    if cid in country_ids and comp_name:
                        competitor_signals[comp_name] = competitor_signals.get(comp_name, 0) + 1

        top_competitor = "N/A"
        top_competitor_signals = 0
        if competitor_signals:
            top_competitor = max(competitor_signals, key=lambda k: competitor_signals[k])
            top_competitor_signals = competitor_signals.get(top_competitor, 0)

        date_note = ""
        if total_7d == total_30d and total_30d > 0:
            date_note = "All signals ingested on Apr 25, 2026. Counts will diverge as new data arrives."

        avg_threat_rationale = f"Average of highest competitor capability scores across {len(countries)} countries in {code} for nivolumab/ipilimumab"
        top_country_rationale = f"Country with most nivolumab/ipilimumab signals in last 30d: {top_country} ({top_country_signals} signals)"
        top_competitor_rationale = f"Competitor with most nivolumab/ipilimumab signals in {code}: {top_competitor} ({top_competitor_signals} signals)"
        calculation_note = date_note or "Metrics calculated from live GeoSignal data. Updated every 60 seconds."

        result.append(
            RegionDashboard(
                region_code=code,
                country_count=len(countries),
                total_signals_7d=total_7d,
                total_signals_30d=total_30d,
                avg_threat_score=avg_threat,
                avg_threat_rationale=avg_threat_rationale,
                top_country_by_threat=top_country,
                top_country_rationale=top_country_rationale,
                top_competitor_by_presence=top_competitor,
                top_competitor_rationale=top_competitor_rationale,
                calculation_note=calculation_note,
            )
        )
    return result


async def _get_summary_data(db: AsyncSession) -> DashboardSummary:
    heatmap = await get_heatmap(
        db=db, region=None, country_code=None, operating_model=None
    )
    competitors = await get_competitors(db=db, region=None, operating_model=None, country_id=None)
    sources = await get_sources(db=db)

    total_signals_30d = sum(c.signal_count_30d for c in heatmap)
    active_countries = sum(1 for c in heatmap if c.signal_count_30d > 0)
    watch_list_competitors = sum(1 for c in competitors if c.watch_list)
    dormant_sources = sum(1 for s in sources if s.status == "DORMANT")

    # Count unique events (distinct event_ids) for nivolumab/ipilimumab in last 30d
    cutoff_30d = datetime.now(UTC) - timedelta(days=30)
    target_molecule_ids = await _get_target_molecule_ids(db)
    unique_result = await db.execute(
        select(func.count(func.distinct(GeoSignal.event_id)))
        .where(GeoSignal.molecule_id.in_(target_molecule_ids))
        .where(GeoSignal.created_at >= cutoff_30d)
    )
    total_signals_unique = unique_result.scalar() or 0

    noise_result = await db.execute(
        select(func.count(NoiseSignal.id)).where(
            NoiseSignal.verification_status == "pending"
        )
    )
    pending_noise = noise_result.scalar() or 0

    total_countries_result = await db.execute(
        select(func.count(Country.id)).where(Country.is_active.is_(True))
    )
    total_countries = total_countries_result.scalar() or 0

    return DashboardSummary(
        total_signals_30d=total_signals_30d,
        total_signals_unique=total_signals_unique,
        active_countries=active_countries,
        total_countries=total_countries,
        watch_list_competitors=watch_list_competitors,
        dormant_sources=dormant_sources,
        pending_noise=pending_noise,
        timestamp=datetime.now(UTC),
        focus_molecules=["nivolumab", "ipilimumab"],
    )


@router.get("/html", response_class=HTMLResponse)
async def get_html_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    heatmap = await get_heatmap(
        db=db, region=None, country_code=None, operating_model=None
    )
    timeline = await get_timeline(
        db=db, region=None, tier=None, source=None, days=30, limit=50,
        country_id=None, operating_model=None
    )
    competitors = await get_competitors(db=db, region=None, operating_model=None, country_id=None)
    sources = await get_sources(db=db)
    regions = await get_regions(db=db, operating_model=None)

    summary = await _get_summary_data(db)

    russia_result = await db.execute(
        select(Country).where(Country.code == "RU")
    )
    russia = russia_result.scalar_one_or_none()
    russia_country_id = str(russia.id) if russia else ""

    all_countries_result = await db.execute(
        select(Country, Region.code)
        .join(Region, Country.region_id == Region.id)
        .where(Country.is_active.is_(True))
    )
    country_models: dict[str, str] = {}
    country_regions: dict[str, str] = {}
    for c, region_code in all_countries_result.all():
        code = cast(str, c.code)
        model = cast(str, c.operating_model.value) if c.operating_model else ""
        region = cast(str, region_code.value) if hasattr(region_code, "value") else str(region_code)
        country_models[code] = model
        country_regions[code] = region

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "heatmap": heatmap,
            "timeline": timeline,
            "competitors": competitors,
            "sources": sources,
            "regions": regions,
            "total_signals": summary.total_signals_30d,
            "total_signals_unique": summary.total_signals_unique,
            "active_countries": summary.active_countries,
            "watch_list_count": summary.watch_list_competitors,
            "dormant_sources": summary.dormant_sources,
            "pending_noise": summary.pending_noise,
            "now": summary.timestamp,
            "russia_country_id": russia_country_id,
            "country_models": country_models,
            "country_regions": country_regions,
        },
    )


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    return await _get_summary_data(db)


@router.get("/json")
async def get_dashboard_json(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return {
        "summary": await get_summary(db=db),
        "heatmap": await get_heatmap(db=db, region=None, country_code=None, operating_model=None),
        "timeline": await get_timeline(db=db, region=None, tier=None, source=None, days=30, limit=50, country_id=None, operating_model=None),
        "competitors": await get_competitors(db=db, region=None, operating_model=None, country_id=None),
        "regions": await get_regions(db=db, operating_model=None),
        "sources": await get_sources(db=db),
    }
