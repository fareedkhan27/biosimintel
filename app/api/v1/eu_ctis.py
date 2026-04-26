from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.eu_ctis import EuCtisEntry, EuCtisRawScrape
from app.models.signal import GeoSignal
from app.schemas.eu_ctis import (
    EuCtisEntryResponse,
    EuCtisRawScrapeResponse,
    EuCtisScrapeResult,
)
from app.schemas.signal import GeoSignalRead
from app.services.eu_ctis import create_signals_from_ctis_entries, scrape_eu_ctis

router = APIRouter()
logger = get_logger(__name__)


def _paginated_response(
    items: list[Any], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/ingestion/eu-ctis/scrape")
async def trigger_eu_ctis_scrape(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EuCtisScrapeResult:
    """Trigger EU CTIS scrape, parse, and signal creation."""
    result = await scrape_eu_ctis(db)
    signals_created = await create_signals_from_ctis_entries(result.scrape_id, db)
    result.signals_created = signals_created
    return result


@router.get("/ingestion/eu-ctis/scrapes")
async def list_scrapes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List raw EU CTIS scrapes, newest first."""
    stmt = select(EuCtisRawScrape).order_by(EuCtisRawScrape.scrape_date.desc())

    count_result = await db.execute(select(select(EuCtisRawScrape).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    scrapes = result.scalars().all()

    items = [EuCtisRawScrapeResponse.model_validate(s) for s in scrapes]
    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/eu-ctis/entries")
async def list_entries(
    molecule_id: UUID | None = Query(None),
    competitor_id: UUID | None = Query(None),
    is_relevant: bool | None = Query(None),
    eu_member_state: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List parsed EU CTIS entries with optional filters."""
    stmt = select(EuCtisEntry).options(
        selectinload(EuCtisEntry.molecule),
        selectinload(EuCtisEntry.competitor),
    )

    if molecule_id:
        stmt = stmt.where(EuCtisEntry.molecule_id == molecule_id)
    if competitor_id:
        stmt = stmt.where(EuCtisEntry.competitor_id == competitor_id)
    if is_relevant is not None:
        stmt = stmt.where(EuCtisEntry.is_relevant == is_relevant)
    if eu_member_state:
        stmt = stmt.where(EuCtisEntry.eu_member_state.ilike(f"%{eu_member_state}%"))
    if status:
        stmt = stmt.where(EuCtisEntry.status.ilike(f"%{status}%"))

    count_result = await db.execute(select(select(EuCtisEntry).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.order_by(EuCtisEntry.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    items = []
    for entry in entries:
        item = EuCtisEntryResponse.model_validate(entry)
        item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
        item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
        items.append(item)

    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/eu-ctis/entries/{entry_id}")
async def get_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EuCtisEntryResponse:
    """Single EU CTIS entry detail with molecule and competitor names."""
    result = await db.execute(
        select(EuCtisEntry)
        .options(selectinload(EuCtisEntry.molecule), selectinload(EuCtisEntry.competitor))
        .where(EuCtisEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    item = EuCtisEntryResponse.model_validate(entry)
    item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
    item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
    return item


@router.get("/ingestion/eu-ctis/signals")
async def list_ctis_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List GeoSignals created from EU CTIS trials."""
    stmt = (
        select(GeoSignal)
        .where(GeoSignal.signal_type == "EU_CTIS_TRIAL")
        .order_by(GeoSignal.created_at.desc())
    )

    count_result = await db.execute(select(select(GeoSignal).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [GeoSignalRead.model_validate(s) for s in signals]
    return _paginated_response(items, total, page, page_size)
