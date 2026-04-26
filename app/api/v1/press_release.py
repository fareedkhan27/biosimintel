from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.db.session import get_db
from app.schemas.press_release import (
    PressReleaseIngestResult,
    PressReleaseRawCreate,
    PressReleaseRawResponse,
)
from app.schemas.signal import GeoSignalRead
from app.services.press_release import PressReleaseService

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


@router.post("/ingestion/press-release")
async def ingest_press_release(
    request: PressReleaseRawCreate,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> PressReleaseIngestResult:
    """Ingest a press release from RSS, webhook, or manual submission."""
    svc = PressReleaseService()
    result = await svc.ingest_press_release(data=request, db=db)
    return result


@router.get("/ingestion/press-release/pending")
async def list_pending_press_releases(
    competitor_id: UUID | None = Query(None),
    source_name: str | None = Query(None),
    signal_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> list[PressReleaseRawResponse]:
    """List pending press releases awaiting human review."""
    svc = PressReleaseService()
    rows = await svc.list_pending(
        db=db,
        competitor_id=competitor_id,
        source_name=source_name,
        signal_type=signal_type,
    )
    items = []
    for pr in rows:
        item = PressReleaseRawResponse.model_validate(pr)
        item.molecule_name = pr.molecule.molecule_name if pr.molecule else None
        item.competitor_name = pr.competitor.canonical_name if pr.competitor else None
        items.append(item)
    return items


@router.post("/ingestion/press-release/{press_release_id}/verify")
async def verify_press_release(
    press_release_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Manually verify a pending press release and create a GeoSignal."""
    svc = PressReleaseService()
    try:
        geo_signal = await svc.verify_press_release(press_release_id=press_release_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(press_release_id),
        "status": "verified",
        "signal_id": str(geo_signal.id),
        "signal_type": geo_signal.signal_type.value,
        "tier": geo_signal.tier,
    }


@router.post("/ingestion/press-release/{press_release_id}/dismiss")
async def dismiss_press_release(
    press_release_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Dismiss a pending press release as noise."""
    svc = PressReleaseService()
    try:
        pr = await svc.dismiss_press_release(press_release_id=press_release_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(pr.id),
        "status": pr.status,
    }


@router.get("/ingestion/press-release/verified")
async def list_verified_press_releases(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> list[PressReleaseRawResponse]:
    """List all verified press releases."""
    svc = PressReleaseService()
    rows = await svc.list_verified(db=db)
    items = []
    for pr in rows:
        item = PressReleaseRawResponse.model_validate(pr)
        item.molecule_name = pr.molecule.molecule_name if pr.molecule else None
        item.competitor_name = pr.competitor.canonical_name if pr.competitor else None
        items.append(item)
    return items


@router.get("/ingestion/press-release/signals")
async def list_press_release_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List GeoSignals created from press releases."""
    svc = PressReleaseService()
    signals, total = await svc.list_press_release_signals(
        db=db, page=page, page_size=page_size
    )
    items = [GeoSignalRead.model_validate(s) for s in signals]
    return _paginated_response(items, total, page, page_size)
