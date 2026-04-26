from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.core.logging import get_logger
from app.db.session import get_db
from app.schemas.social_media import (
    SocialMediaIngestResult,
    SocialMediaRawCreate,
    SocialMediaRawResponse,
    SocialMediaStats,
)
from app.services.social_media import SocialMediaService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/ingestion/social-media")
async def ingest_social_media(
    request: SocialMediaRawCreate,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> SocialMediaIngestResult:
    """Ingest a social media post (Twitter/X or Reddit) — always routes to Noise Block."""
    svc = SocialMediaService()
    result = await svc.ingest_social_media(data=request, db=db)
    return result


@router.get("/ingestion/social-media/pending")
async def list_pending_social_media(
    source_platform: str | None = Query(None),
    competitor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> list[SocialMediaRawResponse]:
    """List all SocialMediaRaw entries with linked NoiseSignal.status = pending."""
    svc = SocialMediaService()
    rows = await svc.list_pending(
        db=db,
        source_platform=source_platform,
        competitor_id=competitor_id,
    )
    items = []
    for row in rows:
        item = SocialMediaRawResponse.model_validate(row)
        item.molecule_name = row.molecule.molecule_name if row.molecule else None
        item.competitor_name = row.competitor.canonical_name if row.competitor else None
        items.append(item)
    return items


@router.get("/ingestion/social-media/stats")
async def get_social_media_stats(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> SocialMediaStats:
    """Return ingestion stats: total, verified, dismissed, expired, by platform."""
    svc = SocialMediaService()
    stats = await svc.get_stats(db=db)
    return SocialMediaStats(
        total_ingested=stats["total_ingested"],
        total_verified=stats["total_verified"],
        total_dismissed=stats["total_dismissed"],
        total_expired=stats["total_expired"],
        by_platform=stats["by_platform"],
    )
