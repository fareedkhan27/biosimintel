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
from app.models.uspto import UsptoEntry, UsptoRawPoll
from app.schemas.signal import GeoSignalRead
from app.schemas.uspto import (
    UsptoEntryResponse,
    UsptoPollResult,
    UsptoRawPollResponse,
)
from app.services.uspto import create_signals_from_uspto_entries, fetch_uspto_data

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


@router.post("/ingestion/uspto/poll")
async def poll_uspto(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> UsptoPollResult:
    """Trigger USPTO PatentsView fetch, parse, and signal creation."""
    result = await fetch_uspto_data(db)
    signals_created = await create_signals_from_uspto_entries(result.poll_id, db)
    result.signals_created = signals_created
    return result


@router.get("/ingestion/uspto/polls")
async def list_polls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List raw USPTO polls, newest first."""
    stmt = select(UsptoRawPoll).order_by(UsptoRawPoll.poll_date.desc())

    count_result = await db.execute(select(select(UsptoRawPoll).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    polls = result.scalars().all()

    items = [UsptoRawPollResponse.model_validate(p) for p in polls]
    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/uspto/entries")
async def list_entries(
    molecule_id: UUID | None = Query(None),
    competitor_id: UUID | None = Query(None),
    is_relevant: bool | None = Query(None),
    patent_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List parsed USPTO entries with optional filters."""
    stmt = select(UsptoEntry).options(
        selectinload(UsptoEntry.molecule),
        selectinload(UsptoEntry.competitor),
    )

    if molecule_id:
        stmt = stmt.where(UsptoEntry.molecule_id == molecule_id)
    if competitor_id:
        stmt = stmt.where(UsptoEntry.competitor_id == competitor_id)
    if is_relevant is not None:
        stmt = stmt.where(UsptoEntry.is_relevant == is_relevant)
    if patent_type:
        stmt = stmt.where(UsptoEntry.patent_type == patent_type)

    count_result = await db.execute(select(select(UsptoEntry).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.order_by(UsptoEntry.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    items = []
    for entry in entries:
        item = UsptoEntryResponse.model_validate(entry)
        item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
        item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
        items.append(item)

    return _paginated_response(items, total, page, page_size)


@router.get("/ingestion/uspto/entries/{entry_id}")
async def get_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> UsptoEntryResponse:
    """Single USPTO entry detail with molecule and competitor names expanded."""
    result = await db.execute(
        select(UsptoEntry)
        .options(selectinload(UsptoEntry.molecule), selectinload(UsptoEntry.competitor))
        .where(UsptoEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    item = UsptoEntryResponse.model_validate(entry)
    item.molecule_name = entry.molecule.molecule_name if entry.molecule else None
    item.competitor_name = entry.competitor.canonical_name if entry.competitor else None
    return item


@router.get("/ingestion/uspto/signals")
async def list_uspto_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List GeoSignals created from USPTO entries."""
    stmt = (
        select(GeoSignal)
        .where(GeoSignal.signal_type == "patent_filing")
        .order_by(GeoSignal.created_at.desc())
    )

    count_result = await db.execute(select(select(GeoSignal).subquery().c.id))
    total = len(count_result.all())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    signals = result.scalars().all()

    items = [GeoSignalRead.model_validate(s) for s in signals]
    return _paginated_response(items, total, page, page_size)
