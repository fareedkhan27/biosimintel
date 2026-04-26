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
from app.models.signal import GeoSignal
from app.models.who_ictrp import WhoIctrpEntry, WhoIctrpRawPoll
from app.schemas.signal import GeoSignalRead
from app.schemas.who_ictrp import (
    WhoIctrpEntryResponse,
    WhoIctrpPollResult,
    WhoIctrpRawPollResponse,
)
from app.services.who_ictrp import create_signals_from_ictrp_entries, fetch_who_ictrp_data

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


@router.post("/ingestion/who-ictrp/poll")
async def poll_who_ictrp(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> WhoIctrpPollResult:
    """Trigger WHO ICTRP bulk download, parse, and signal creation."""
    result = await fetch_who_ictrp_data(db)
    signals_created = await create_signals_from_ictrp_entries(result.poll_id, db)
    result.signals_created = signals_created
    return result


@router.get("/ingestion/who-ictrp/polls")
async def list_polls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List raw WHO ICTRP polls, newest first."""
    stmt = select(WhoIctrpRawPoll).order_by(WhoIctrpRawPoll.poll_month.desc())

    count_result = await db.execute(select(select(WhoIctrpRawPoll).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    polls = result.scalars().all()

    items = [WhoIctrpRawPollResponse.model_validate(p) for p in polls]
    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/who-ictrp/entries")
async def list_entries(
    molecule_id: UUID | None = Query(None),
    competitor_id: UUID | None = Query(None),
    is_relevant: bool | None = Query(None),
    source_register: str | None = Query(None),
    recruitment_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List parsed WHO ICTRP entries with optional filters."""
    stmt = select(WhoIctrpEntry).options(
        selectinload(WhoIctrpEntry.molecule),
        selectinload(WhoIctrpEntry.competitor),
    )

    if molecule_id:
        stmt = stmt.where(WhoIctrpEntry.molecule_id == molecule_id)
    if competitor_id:
        stmt = stmt.where(WhoIctrpEntry.competitor_id == competitor_id)
    if is_relevant is not None:
        stmt = stmt.where(WhoIctrpEntry.is_relevant == is_relevant)
    if source_register:
        stmt = stmt.where(WhoIctrpEntry.source_register.ilike(source_register))
    if recruitment_status:
        stmt = stmt.where(WhoIctrpEntry.recruitment_status.ilike(recruitment_status))

    count_result = await db.execute(select(select(WhoIctrpEntry).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.order_by(WhoIctrpEntry.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    items = []
    for entry in entries:
        item = WhoIctrpEntryResponse.model_validate(entry)
        item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
        item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
        items.append(item)

    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/who-ictrp/entries/{entry_id}")
async def get_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> WhoIctrpEntryResponse:
    """Single WHO ICTRP entry detail with molecule and competitor names expanded."""
    result = await db.execute(
        select(WhoIctrpEntry)
        .options(selectinload(WhoIctrpEntry.molecule), selectinload(WhoIctrpEntry.competitor))
        .where(WhoIctrpEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    item = WhoIctrpEntryResponse.model_validate(entry)
    item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
    item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
    return item


@router.get("/ingestion/who-ictrp/signals")
async def list_ictrp_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List GeoSignals created from WHO ICTRP entries."""
    stmt = (
        select(GeoSignal)
        .where(GeoSignal.source_type == "who_ictrp")
        .order_by(GeoSignal.created_at.desc())
    )

    count_result = await db.execute(select(select(GeoSignal).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [GeoSignalRead.model_validate(s) for s in signals]
    return _paginated_response(items, total, page, page_size)
