from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.combo import CompetitorMoleculeAssignment
from app.models.competitor import Competitor
from app.models.event import Event
from app.models.geo import Country, Region
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal
from app.models.signal import GeoSignal
from app.schemas.dashboard import (
    CompetitorDashboard,
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


def _threat_level(score: int, has_signals: bool = True) -> str:
    if not has_signals or score == 0:
        return "MONITORING"
    if score <= 44:
        return "LOW"
    if score <= 74:
        return "MEDIUM"
    if score <= 89:
        return "HIGH"
    return "CRITICAL"


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

    stmt = (
        select(Country, Region)
        .join(Region, Country.region_id == Region.id)
        .where(Country.is_active.is_(True))
    )
    if region:
        stmt = stmt.where(Region.code == region.upper())
    if country_code:
        stmt = stmt.where(Country.code == country_code.upper())
    if operating_model:
        stmt = stmt.where(Country.operating_model == operating_model.upper())
    stmt = stmt.order_by(Country.code)
    countries_result = await db.execute(stmt)
    countries = [(c, r) for c, r in countries_result.all()]

    signals_result = await db.execute(
        select(GeoSignal, Event, Competitor)
        .join(Event, GeoSignal.event_id == Event.id, isouter=True)
        .join(Competitor, GeoSignal.competitor_id == Competitor.id, isouter=True)
        .where(GeoSignal.created_at >= cutoff_30d)
    )
    signals = signals_result.all()

    aggregates: dict[UUID, dict[str, Any]] = {
        cast(UUID, c.id): {
            "signals_7d": 0,
            "signals_30d": 0,
            "max_threat": 0,
            "competitor_signals": {},
        }
        for c, _ in countries
    }

    for gs, event, competitor in signals:
        if not gs.country_ids:
            continue
        threat = event.threat_score if event and event.threat_score is not None else 0
        comp_name = competitor.canonical_name if competitor else "Unknown"
        for cid in gs.country_ids:
            if cid not in aggregates:
                continue
            agg = aggregates[cid]
            agg["signals_30d"] += 1
            if gs.created_at >= cutoff_7d:
                agg["signals_7d"] += 1
            if threat > agg["max_threat"]:
                agg["max_threat"] = threat
            # Track signal count per competitor for this country
            comp_id = str(competitor.id) if competitor else "unknown"
            agg["competitor_signals"][comp_id] = agg["competitor_signals"].get(comp_id, {"count": 0, "name": comp_name})
            agg["competitor_signals"][comp_id]["count"] += 1

    result: list[HeatmapCountry] = []
    for c, r in countries:
        cid = cast(UUID, c.id)
        agg = aggregates[cid]
        has_signals = agg["signals_30d"] > 0
        score = agg["max_threat"]
        # Pick top competitor by signal count, tie-break by highest threat
        top_comp = "Unknown"
        if agg["competitor_signals"]:
            top_comp_entry = max(
                agg["competitor_signals"].values(),
                key=lambda x: (x["count"], x["name"])
            )
            top_comp = top_comp_entry["name"]
        result.append(
            HeatmapCountry(
                country_code=cast(str, c.code),
                country_name=cast(str, c.name),
                region=cast(str, r.code.value) if r.code else "",
                highest_competitor_threat_score=score,
                threat_level=cast(Any, _threat_level(score, has_signals)),
                top_competitor_name=top_comp if has_signals else "Unknown",
                signal_count_7d=agg["signals_7d"],
                signal_count_30d=agg["signals_30d"],
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

    stmt = (
        select(GeoSignal, Event, Competitor)
        .join(Event, GeoSignal.event_id == Event.id, isouter=True)
        .join(Competitor, GeoSignal.competitor_id == Competitor.id, isouter=True)
        .where(GeoSignal.created_at >= cutoff)
    )

    if tier is not None:
        stmt = stmt.where(GeoSignal.tier == tier)
    if source:
        stmt = stmt.where(GeoSignal.source_type == source)

    if region:
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
        model_country_result = await db.execute(
            select(Country.id).where(Country.operating_model == operating_model.upper())
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
    country_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[CompetitorDashboard]:
    competitors_result = await db.execute(
        select(Competitor).order_by(Competitor.canonical_name)
    )
    competitors = list(competitors_result.scalars().all())

    if not competitors:
        return []

    competitor_ids = [cast(UUID, c.id) for c in competitors]

    molecule_result = await db.execute(
        select(Molecule).where(
            Molecule.id.in_([c.molecule_id for c in competitors if c.molecule_id])
        )
    )
    molecules_map = {
        cast(UUID, m.id): cast(str, m.molecule_name) for m in molecule_result.scalars().all()
    }

    assignments_result = await db.execute(
        select(CompetitorMoleculeAssignment, Molecule)
        .join(Molecule, CompetitorMoleculeAssignment.molecule_id == Molecule.id)
        .where(CompetitorMoleculeAssignment.competitor_id.in_(competitor_ids))
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
        .order_by(GeoSignal.created_at.desc())
    )
    comp_signals: dict[UUID, list[tuple[GeoSignal, Event | None]]] = {
        cid: [] for cid in competitor_ids
    }
    comp_countries: dict[UUID, set[UUID]] = {cid: set() for cid in competitor_ids}
    for gs, event in signals_result.all():
        comp_signals[cast(UUID, gs.competitor_id)].append((gs, event))
        if gs.country_ids:
            comp_countries[cast(UUID, gs.competitor_id)].update(gs.country_ids)

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
        primary = molecules_map.get(cast(UUID, c.molecule_id))
        if primary and primary not in molecules:
            molecules.insert(0, primary)

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
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)

    counts_result = await db.execute(
        select(GeoSignal.source_type, func.count(GeoSignal.id)).group_by(
            GeoSignal.source_type
        )
    )
    total_counts: dict[str | None, int] = {}
    for source_type, count in counts_result.all():
        total_counts[source_type] = count

    counts_7d_result = await db.execute(
        select(GeoSignal.source_type, func.count(GeoSignal.id))
        .where(GeoSignal.created_at >= cutoff_7d)
        .group_by(GeoSignal.source_type)
    )
    counts_7d: dict[str | None, int] = {}
    for source_type, count in counts_7d_result.all():
        counts_7d[source_type] = count

    last_poll_result = await db.execute(
        select(GeoSignal.source_type, func.max(GeoSignal.created_at)).group_by(
            GeoSignal.source_type
        )
    )
    last_polls: dict[str | None, datetime] = {}
    for source_type, max_dt in last_poll_result.all():
        last_polls[source_type] = max_dt

    result: list[SourceHealth] = []
    for source_name, status in _SOURCES.items():
        if status == "DORMANT":
            result.append(
                SourceHealth(
                    source_name=source_name,
                    status="DORMANT",
                    last_poll_timestamp=None,
                    signal_count_total=0,
                    signal_count_7d=0,
                )
            )
        else:
            result.append(
                SourceHealth(
                    source_name=source_name,
                    status="ACTIVE",
                    last_poll_timestamp=last_polls.get(source_name),
                    signal_count_total=total_counts.get(source_name, 0),
                    signal_count_7d=counts_7d.get(source_name, 0),
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

    regions_result = await db.execute(select(Region).order_by(Region.code))
    regions = list(regions_result.scalars().all())

    countries_stmt = (
        select(Country, Region.code)
        .join(Region, Country.region_id == Region.id)
        .where(Country.is_active.is_(True))
    )
    if operating_model:
        countries_stmt = countries_stmt.where(
            Country.operating_model == operating_model.upper()
        )
    countries_result = await db.execute(countries_stmt)
    region_countries: dict[str, list[Country]] = {}
    region_country_ids: dict[str, list[UUID]] = {}
    for country, region_code in countries_result.all():
        code = (
            cast(str, region_code.value)
            if hasattr(region_code, "value")
            else str(region_code)
        )
        region_countries.setdefault(code, []).append(country)
        region_country_ids.setdefault(code, []).append(cast(UUID, country.id))

    signals_result = await db.execute(
        select(GeoSignal, Event, Competitor)
        .join(Event, GeoSignal.event_id == Event.id, isouter=True)
        .join(Competitor, GeoSignal.competitor_id == Competitor.id, isouter=True)
        .where(GeoSignal.created_at >= cutoff_30d)
    )
    signals = signals_result.all()

    result: list[RegionDashboard] = []
    for region in regions:
        code = cast(str, region.code.value) if region.code else ""
        countries = region_countries.get(code, [])
        country_ids = region_country_ids.get(code, [])
        country_id_set = set(country_ids)

        total_7d = 0
        total_30d = 0
        country_max_threat: dict[UUID, int] = {}
        competitor_signals: dict[str, int] = {}

        for gs, event, competitor in signals:
            if not gs.country_ids:
                continue
            if not any(cid in country_id_set for cid in gs.country_ids):
                continue

            total_30d += 1
            if gs.created_at >= cutoff_7d:
                total_7d += 1

            threat = event.threat_score if event and event.threat_score is not None else 0
            for cid in gs.country_ids:
                if cid in country_id_set and threat > country_max_threat.get(cid, 0):
                    country_max_threat[cid] = threat

            if competitor:
                comp_name = cast(str, competitor.canonical_name)
                competitor_signals[comp_name] = competitor_signals.get(comp_name, 0) + 1

        avg_threat = 0.0
        if countries:
            avg_threat = round(
                sum(country_max_threat.get(cast(UUID, c.id), 0) for c in countries)
                / len(countries),
                1,
            )

        top_country = "N/A"
        top_country_signals = 0
        if country_max_threat:
            top_cid = max(country_max_threat, key=lambda k: country_max_threat[k])
            top_country_obj = next(
                (c for c in countries if cast(UUID, c.id) == top_cid), None
            )
            top_country = cast(str, top_country_obj.name) if top_country_obj else "N/A"
            top_country_signals = country_max_threat.get(top_cid, 0)

        top_competitor = "N/A"
        top_competitor_signals = 0
        if competitor_signals:
            top_competitor = max(competitor_signals, key=lambda k: competitor_signals[k])
            top_competitor_signals = competitor_signals.get(top_competitor, 0)

        avg_threat_rationale = "Average of highest competitor threat scores across all countries in region"
        top_country_rationale = f"Country with highest threat score: {top_country} (score: {top_country_signals})"
        top_competitor_rationale = f"Competitor with most signals in region: {top_competitor} ({top_competitor_signals} signals)"
        calculation_note = "Metrics calculated from live GeoSignal data. Updated every 60 seconds."

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
    competitors = await get_competitors(db=db, country_id=None)
    sources = await get_sources(db=db)
    regions = await get_regions(db=db, operating_model=None)

    total_signals = sum(c.signal_count_30d for c in heatmap)
    active_countries = sum(1 for c in heatmap if c.signal_count_30d > 0)
    watch_list_count = sum(1 for c in competitors if c.watch_list)
    dormant_sources = sum(1 for s in sources if s.status == "DORMANT")

    noise_result = await db.execute(
        select(func.count(NoiseSignal.id)).where(
            NoiseSignal.verification_status == "pending"
        )
    )
    pending_noise = noise_result.scalar() or 0

    now = datetime.now(UTC)

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
            "total_signals": total_signals,
            "active_countries": active_countries,
            "watch_list_count": watch_list_count,
            "dormant_sources": dormant_sources,
            "pending_noise": pending_noise,
            "now": now,
            "russia_country_id": russia_country_id,
            "country_models": country_models,
            "country_regions": country_regions,
        },
    )
