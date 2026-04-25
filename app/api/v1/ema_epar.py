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
from app.models.ema_epar import EmaEparEntry, EmaEparRawPoll
from app.models.signal import GeoSignal
from app.schemas.ema_epar import (
    EmaEparEntryResponse,
    EmaEparPollResult,
    EmaEparRawPollResponse,
)
from app.schemas.signal import GeoSignalRead
from app.services.ema_epar import create_signals_from_epar_entries, fetch_ema_epar_data

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


@router.post("/ingestion/ema-epar/poll")
async def poll_ema_epar(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EmaEparPollResult:
    """Trigger EMA EPAR fetch, parse, and signal creation."""
    result = await fetch_ema_epar_data(db)
    signals_created = await create_signals_from_epar_entries(result.poll_id, db)
    result.signals_created = signals_created
    return result


@router.get("/ingestion/ema-epar/polls")
async def list_polls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List raw EMA EPAR polls, newest first."""
    stmt = select(EmaEparRawPoll).order_by(EmaEparRawPoll.poll_date.desc())

    count_result = await db.execute(select(select(EmaEparRawPoll).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    polls = result.scalars().all()

    items = [EmaEparRawPollResponse.model_validate(p) for p in polls]
    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/ema-epar/entries")
async def list_entries(
    molecule_id: UUID | None = Query(None),
    competitor_id: UUID | None = Query(None),
    is_relevant: bool | None = Query(None),
    active_substance: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List parsed EMA EPAR entries with optional filters."""
    stmt = select(EmaEparEntry).options(
        selectinload(EmaEparEntry.molecule),
        selectinload(EmaEparEntry.competitor),
    )

    if molecule_id:
        stmt = stmt.where(EmaEparEntry.molecule_id == molecule_id)
    if competitor_id:
        stmt = stmt.where(EmaEparEntry.competitor_id == competitor_id)
    if is_relevant is not None:
        stmt = stmt.where(EmaEparEntry.is_relevant == is_relevant)
    if active_substance:
        stmt = stmt.where(
            EmaEparEntry.active_substance.ilike(f"%{active_substance}%")
        )

    count_result = await db.execute(select(select(EmaEparEntry).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.order_by(EmaEparEntry.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    items = []
    for entry in entries:
        item = EmaEparEntryResponse.model_validate(entry)
        item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
        item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
        items.append(item)

    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/ema-epar/entries/{entry_id}")
async def get_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EmaEparEntryResponse:
    """Single EMA EPAR entry detail with molecule and competitor names."""
    result = await db.execute(
        select(EmaEparEntry)
        .options(selectinload(EmaEparEntry.molecule), selectinload(EmaEparEntry.competitor))
        .where(EmaEparEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    item = EmaEparEntryResponse.model_validate(entry)
    item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
    item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
    return item


@router.get("/ingestion/ema-epar/signals")
async def list_epar_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List GeoSignals created from EMA EPAR approvals."""
    stmt = (
        select(GeoSignal)
        .where(GeoSignal.signal_type == "ema_epar_approval")
        .order_by(GeoSignal.created_at.desc())
    )

    count_result = await db.execute(select(select(GeoSignal).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [GeoSignalRead.model_validate(s) for s in signals]
    return _paginated_response(items, total, page, page_size)
