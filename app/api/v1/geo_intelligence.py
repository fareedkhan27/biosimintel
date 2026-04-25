from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.db.session import get_db
from app.models.competitor import Competitor
from app.models.geo import CompetitorCapability, Country, Region
from app.models.molecule import Molecule
from app.models.signal import GeoSignal
from app.schemas.signal import GeoSignalRead
from app.services.combo_service import ComboIntelligenceService
from app.services.noise_service import NoiseBlockService
from app.services.threat_service import GeoThreatScorer

router = APIRouter()


def _paginated_response(
    items: list[Any], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/regions")
async def list_regions(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    result = await db.execute(select(Region))
    regions = result.scalars().all()

    data: list[dict[str, Any]] = []
    for region in regions:
        count_result = await db.execute(
            select(func.count(Country.id)).where(Country.region_id == region.id)
        )
        country_count = count_result.scalar() or 0
        data.append({
            "id": str(cast(UUID, region.id)),
            "name": region.name,
            "code": cast(str, region.code.value) if region.code else "",
            "country_count": country_count,
        })

    return {"regions": data}


@router.get("/regions/{code}")
async def get_region(
    code: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    result = await db.execute(select(Region).where(Region.code == code.upper()))
    region = result.scalar_one_or_none()
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")

    country_result = await db.execute(
        select(Country).where(Country.region_id == region.id)
    )
    countries = country_result.scalars().all()

    return {
        "id": str(cast(UUID, region.id)),
        "name": region.name,
        "code": cast(str, region.code.value) if region.code else "",
        "countries": [
            {
                "id": str(cast(UUID, c.id)),
                "name": c.name,
                "code": c.code,
                "operating_model": cast(str, c.operating_model.value) if c.operating_model else "",
            }
            for c in countries
        ],
    }


@router.get("/countries")
async def list_countries(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    region: str | None = Query(None),
    operating_model: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    stmt = select(Country)

    if region:
        region_result = await db.execute(
            select(Region).where(Region.code == region.upper())
        )
        region_obj = region_result.scalar_one_or_none()
        if region_obj:
            stmt = stmt.where(Country.region_id == region_obj.id)

    if operating_model:
        stmt = stmt.where(Country.operating_model == operating_model.upper())

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    countries = result.scalars().all()

    items = [
        {
            "id": str(cast(UUID, c.id)),
            "name": c.name,
            "code": c.code,
            "operating_model": cast(str, c.operating_model.value) if c.operating_model else "",
            "region_id": str(cast(UUID, c.region_id)) if c.region_id else None,
        }
        for c in countries
    ]

    return _paginated_response(items, total, page, page_size)


@router.get("/countries/{code}")
async def get_country(
    code: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    result = await db.execute(select(Country).where(Country.code == code.upper()))
    country = result.scalar_one_or_none()
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")

    region_name = ""
    if country.region_id:
        region_result = await db.execute(
            select(Region).where(Region.id == country.region_id)
        )
        region = region_result.scalar_one_or_none()
        if region:
            region_name = cast(str, region.name) or ""

    threat_summary: dict[str, Any] = {}
    try:
        scorer = GeoThreatScorer()
        threat_summary = await scorer.get_country_threat_summary(code.upper())
    except Exception:
        threat_summary = {"high": 0, "medium": 0, "low": 0, "competitors": []}

    return {
        "id": str(cast(UUID, country.id)),
        "name": country.name,
        "code": country.code,
        "operating_model": cast(str, country.operating_model.value) if country.operating_model else "",
        "region": region_name,
        "threat_summary": threat_summary,
    }


@router.get("/signals")
async def list_signals(
    region: str | None = Query(None),
    department: str | None = Query(None),
    tier: int | None = Query(None, ge=1, le=3),
    since: str | None = Query(None),
    competitor_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    stmt = select(GeoSignal)

    if competitor_id:
        stmt = stmt.where(GeoSignal.competitor_id == competitor_id)
    if tier is not None:
        stmt = stmt.where(GeoSignal.tier == tier)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            stmt = stmt.where(GeoSignal.created_at >= since_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid since format") from None

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

    if department:
        stmt = stmt.where(GeoSignal.department_tags.contains([department.lower()]))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.order_by(GeoSignal.relevance_score.desc(), GeoSignal.tier.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [_enrich_signal(db, s) for s in signals]
    await _resolve_signal_names(db, items)

    return _paginated_response(items, total, page, page_size)


@router.get("/signals/delta")
async def get_signals_delta(
    region: str,
    since: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid since format") from exc

    try:
        region_result = await db.execute(
            select(Region).where(Region.code == region.upper())
        )
        region_obj = region_result.scalar_one_or_none()
    except Exception:
        region_obj = None

    if region_obj is None:
        return {"region": region, "since": since, "signals": [], "count": 0}

    country_result = await db.execute(
        select(Country.id).where(Country.region_id == region_obj.id)
    )
    region_country_ids = [row[0] for row in country_result.all()]

    stmt = (
        select(GeoSignal)
        .where(GeoSignal.created_at >= since_dt)
        .where(GeoSignal.country_ids.overlap(region_country_ids))
        .order_by(GeoSignal.relevance_score.desc(), GeoSignal.tier.asc())
    )
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [_enrich_signal(db, s) for s in signals]
    await _resolve_signal_names(db, items)

    return {
        "region": region,
        "since": since,
        "signals": items,
        "count": len(items),
    }


@router.get("/signals/{signal_id}")
async def get_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> GeoSignalRead:
    result = await db.execute(select(GeoSignal).where(GeoSignal.id == signal_id))
    signal = result.scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    item = _enrich_signal(db, signal)
    await _resolve_signal_names(db, [item])
    return GeoSignalRead(**item)


@router.get("/competitors/{competitor_id}/geo-profile")
async def get_competitor_geo_profile(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    comp_result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = comp_result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    cap_result = await db.execute(
        select(CompetitorCapability, Region)
        .join(Region, CompetitorCapability.region_id == Region.id)
        .where(CompetitorCapability.competitor_id == competitor_id)
    )
    capabilities: list[dict[str, Any]] = []
    for cap, region in cap_result.all():
        capabilities.append({
            "region": cast(str, region.code.value) if region.code else "",
            "region_name": region.name,
            "confidence": cap.confidence_score,
            "has_local_manufacturing": cap.has_local_manufacturing,
            "has_local_regulatory_filing": cap.has_local_regulatory_filing,
            "has_local_commercial_infrastructure": cap.has_local_commercial_infrastructure,
        })

    combo_data: dict[str, Any] = {}
    try:
        combo_svc = ComboIntelligenceService()
        matrix = await combo_svc.get_combo_threat_matrix()
        for entry in matrix:
            if entry.get("competitor") == competitor.canonical_name:
                combo_data = {
                    "nivolumab_asset": entry.get("nivolumab_asset"),
                    "ipilimumab_asset": entry.get("ipilimumab_asset"),
                    "capability": entry.get("combo_capability"),
                    "threat": entry.get("threat_level"),
                }
                break
    except Exception:
        pass

    return {
        "competitor_id": str(competitor_id),
        "name": competitor.canonical_name,
        "capabilities": capabilities,
        "combo": combo_data,
    }


@router.get("/competitors/{competitor_id}/signals")
async def get_competitor_signals(
    competitor_id: UUID,
    since: str | None = Query(None),
    tier: int | None = Query(None, ge=1, le=3),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    stmt = select(GeoSignal).where(GeoSignal.competitor_id == competitor_id)

    if tier is not None:
        stmt = stmt.where(GeoSignal.tier == tier)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            stmt = stmt.where(GeoSignal.created_at >= since_dt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid since format") from exc

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.order_by(GeoSignal.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [_enrich_signal(db, s) for s in signals]
    await _resolve_signal_names(db, items)

    return _paginated_response(items, total, page, page_size)


@router.get("/dashboard/region/{code}")
async def get_region_dashboard(
    code: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    region_result = await db.execute(
        select(Region).where(Region.code == code.upper())
    )
    region = region_result.scalar_one_or_none()
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")

    country_result = await db.execute(
        select(Country).where(Country.region_id == region.id)
    )
    countries = country_result.scalars().all()
    country_ids = [cast(UUID, c.id) for c in countries]

    since = datetime.now(UTC) - timedelta(days=7)

    # Active signals count
    active_stmt = select(func.count()).where(
        GeoSignal.country_ids.overlap(country_ids),
        GeoSignal.created_at >= since,
    )
    active_result = await db.execute(active_stmt)
    active_signals_count = active_result.scalar() or 0

    # Threat heatmap
    heatmap_data: dict[str, Any] = {}
    try:
        scorer = GeoThreatScorer()
        heatmap_data = await scorer.get_region_threat_heatmap(code.upper())
    except Exception:
        heatmap_data = {}

    # Latest signals
    latest_stmt = (
        select(GeoSignal)
        .where(GeoSignal.country_ids.overlap(country_ids))
        .where(GeoSignal.created_at >= since)
        .order_by(GeoSignal.created_at.desc())
        .limit(5)
    )
    latest_result = await db.execute(latest_stmt)
    latest_signals = latest_result.scalars().all()

    latest_items: list[dict[str, Any]] = []
    for s in latest_signals:
        comp_name = ""
        if s.competitor_id:
            comp_r = await db.execute(
                select(Competitor).where(Competitor.id == s.competitor_id)
            )
            comp = comp_r.scalar_one_or_none()
            if comp:
                comp_name = cast(str, comp.canonical_name) or ""
        latest_items.append({
            "id": str(cast(UUID, s.id)),
            "signal_type": cast(str, s.signal_type.value),
            "competitor": comp_name,
            "tier": s.tier,
            "relevance_score": s.relevance_score,
        })

    # Noise digest
    noise_digest: list[dict[str, Any]] = []
    try:
        noise_svc = NoiseBlockService()
        noise_digest = await noise_svc.get_noise_digest(
            code.upper(), datetime.now(UTC) - timedelta(days=7)
        )
    except Exception:
        pass

    # Top competitors
    top_competitors: list[dict[str, Any]] = []
    try:
        combo_svc = ComboIntelligenceService()
        matrix = await combo_svc.get_combo_threat_matrix()
        for entry in matrix[:5]:
            top_competitors.append({
                "name": entry.get("competitor", ""),
                "asset": entry.get("nivolumab_asset", ""),
                "threat_level": entry.get("threat_level", ""),
                "relevance_score": 0,
            })
    except Exception:
        pass

    return {
        "region": code.upper(),
        "region_name": region.name,
        "countries_count": len(countries),
        "active_signals_count": active_signals_count,
        "high_threat_count": heatmap_data.get("high_threat_count", 0),
        "medium_threat_count": heatmap_data.get("medium_threat_count", 0),
        "low_threat_count": heatmap_data.get("low_threat_count", 0),
        "top_competitors": top_competitors,
        "latest_signals": latest_items,
        "noise_digest": noise_digest,
    }


@router.get("/dashboard/country/{code}")
async def get_country_dashboard(
    code: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    country_result = await db.execute(
        select(Country).where(Country.code == code.upper())
    )
    country = country_result.scalar_one_or_none()
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")

    region_name = ""
    if country.region_id:
        region_result = await db.execute(
            select(Region).where(Region.id == country.region_id)
        )
        region = region_result.scalar_one_or_none()
        if region:
            region_name = cast(str, region.name) or ""

    since = datetime.now(UTC) - timedelta(days=7)

    # Threat summary
    threat_summary: dict[str, Any] = {}
    try:
        scorer = GeoThreatScorer()
        threat_summary = await scorer.get_country_threat_summary(code.upper())
    except Exception:
        threat_summary = {"competitors": []}

    competitor_threats = [
        {
            "competitor": c.get("competitor_name", ""),
            "asset": c.get("asset_name", ""),
            "relevance_score": c.get("relevance_score", 0),
            "threat_level": c.get("threat_level", ""),
        }
        for c in threat_summary.get("competitors", [])
    ]

    # Latest signals
    country_uuid = cast(UUID, country.id)
    latest_stmt = (
        select(GeoSignal)
        .where(GeoSignal.country_ids.overlap([country_uuid]))
        .where(GeoSignal.created_at >= since)
        .order_by(GeoSignal.created_at.desc())
        .limit(5)
    )
    latest_result = await db.execute(latest_stmt)
    latest_signals = latest_result.scalars().all()

    latest_items: list[dict[str, Any]] = []
    for s in latest_signals:
        comp_name = ""
        if s.competitor_id:
            comp_r = await db.execute(
                select(Competitor).where(Competitor.id == s.competitor_id)
            )
            comp = comp_r.scalar_one_or_none()
            if comp:
                comp_name = cast(str, comp.canonical_name) or ""
        latest_items.append({
            "id": str(cast(UUID, s.id)),
            "signal_type": cast(str, s.signal_type.value),
            "competitor": comp_name,
            "tier": s.tier,
            "relevance_score": s.relevance_score,
        })

    # Noise count
    noise_count = 0
    try:
        noise_svc = NoiseBlockService()
        noise_digest = await noise_svc.get_noise_digest(
            region_name.upper().replace(" ", "_") if region_name else "",
            datetime.now(UTC) - timedelta(days=7),
        )
        noise_count = len(noise_digest)
    except Exception:
        pass

    return {
        "country": country.name,
        "code": country.code,
        "operating_model": cast(str, country.operating_model.value) if country.operating_model else "",
        "region": region_name,
        "competitor_threats": competitor_threats,
        "latest_signals": latest_items,
        "noise_count": noise_count,
    }


def _enrich_signal(_db: AsyncSession, signal: GeoSignal) -> dict[str, Any]:
    return {
        "id": str(cast(UUID, signal.id)),
        "event_id": str(signal.event_id) if signal.event_id else None,
        "competitor_id": str(signal.competitor_id) if signal.competitor_id else None,
        "molecule_id": str(signal.molecule_id),
        "region_id": str(signal.region_id) if signal.region_id else None,
        "country_ids": [str(cid) for cid in cast(list[UUID], signal.country_ids)] if signal.country_ids else [],
        "signal_type": cast(str, signal.signal_type.value),
        "confidence": cast(str, signal.confidence.value),
        "relevance_score": signal.relevance_score or 0,
        "department_tags": signal.department_tags or [],
        "operating_model_relevance": cast(str, signal.operating_model_relevance.value),
        "delta_note": signal.delta_note,
        "source_url": signal.source_url,
        "source_type": signal.source_type,
        "tier": signal.tier or 3,
        "expires_at": signal.expires_at.isoformat() if signal.expires_at else None,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
        "updated_at": signal.updated_at.isoformat() if signal.updated_at else None,
        "competitor_name": None,
        "molecule_name": None,
        "region_name": None,
        "country_names": None,
    }


async def _resolve_signal_names(
    db: AsyncSession, items: list[dict[str, Any]]
) -> None:
    competitor_ids = {item["competitor_id"] for item in items if item.get("competitor_id")}
    molecule_ids = {item["molecule_id"] for item in items if item.get("molecule_id")}
    region_ids = {item["region_id"] for item in items if item.get("region_id")}
    country_ids: set[str] = set()
    for item in items:
        for cid in item.get("country_ids", []):
            country_ids.add(cid)

    competitor_names: dict[str, str] = {}
    if competitor_ids:
        result = await db.execute(
            select(Competitor).where(Competitor.id.in_(competitor_ids))
        )
        for c in result.scalars().all():
            competitor_names[str(cast(UUID, c.id))] = cast(str, c.canonical_name) or ""

    molecule_names: dict[str, str] = {}
    if molecule_ids:
        result = await db.execute(
            select(Molecule).where(Molecule.id.in_(molecule_ids))
        )
        for m in result.scalars().all():
            molecule_names[str(cast(UUID, m.id))] = m.molecule_name or ""

    region_names: dict[str, str] = {}
    if region_ids:
        result = await db.execute(
            select(Region).where(Region.id.in_(region_ids))
        )
        for r in result.scalars().all():
            region_names[str(cast(UUID, r.id))] = r.name or ""

    country_names_map: dict[str, str] = {}
    if country_ids:
        uuids = {UUID(cid) for cid in country_ids}
        result = await db.execute(select(Country).where(Country.id.in_(uuids)))
        for c in result.scalars().all():
            country_names_map[str(cast(UUID, c.id))] = c.name or ""

    for item in items:
        if item.get("competitor_id"):
            item["competitor_name"] = competitor_names.get(item["competitor_id"], "")
        if item.get("molecule_id"):
            item["molecule_name"] = molecule_names.get(item["molecule_id"], "")
        if item.get("region_id"):
            item["region_name"] = region_names.get(item["region_id"], "")
        item["country_names"] = [
            country_names_map.get(cid, "") for cid in item.get("country_ids", [])
        ]
