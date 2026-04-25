from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.db.session import get_db
from app.services.noise_service import NoiseBlockService

router = APIRouter()


class IngestNoiseRequest(BaseModel):
    raw_text: str
    source_type: str = Field(default="social", max_length=20)
    source_url: str | None = None
    source_author: str | None = Field(None, max_length=100)


class VerifyNoiseRequest(BaseModel):
    verification_notes: str
    verified_by: str = Field(..., max_length=100)


class DismissNoiseRequest(BaseModel):
    dismissed_by: str = Field(..., max_length=100)


class ExpireResponse(BaseModel):
    expired_count: int
    timestamp: str


@router.post("/noise")
async def ingest_noise(
    request: IngestNoiseRequest,
    _db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    svc = NoiseBlockService()
    noise = await svc.ingest_noise(
        raw_text=request.raw_text,
        source_type=request.source_type,
        source_url=request.source_url,
        source_author=request.source_author,
    )
    return {
        "id": str(noise.id),
        "raw_text": noise.raw_text,
        "source_type": noise.source_type.value,
        "verification_status": noise.verification_status.value,
        "flagged_at": noise.flagged_at.isoformat() if noise.flagged_at else None,
    }


@router.post("/noise/{noise_id}/verify")
async def verify_noise(
    noise_id: UUID,
    request: VerifyNoiseRequest,
    _db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    svc = NoiseBlockService()
    try:
        noise = await svc.verify_noise(
            noise_id=noise_id,
            verification_notes=request.verification_notes,
            verified_by=request.verified_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(noise.id),
        "verification_status": noise.verification_status.value,
        "verified_at": noise.verified_at.isoformat() if noise.verified_at else None,
        "verified_by": noise.verified_by,
    }


@router.post("/noise/{noise_id}/dismiss")
async def dismiss_noise(
    noise_id: UUID,
    request: DismissNoiseRequest,
    _db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    svc = NoiseBlockService()
    try:
        noise = await svc.dismiss_noise(
            noise_id=noise_id,
            dismissed_by=request.dismissed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(noise.id),
        "verification_status": noise.verification_status.value,
        "dismissed_at": noise.dismissed_at.isoformat() if noise.dismissed_at else None,
        "dismissed_by": noise.dismissed_by,
    }


@router.post("/noise/{noise_id}/escalate")
async def escalate_noise(
    noise_id: UUID,
    _db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    svc = NoiseBlockService()
    try:
        noise = await svc.escalate_noise(noise_id=noise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(noise.id),
        "escalation_count": noise.escalation_count,
        "verification_status": noise.verification_status.value,
    }


@router.get("/noise/digest")
async def get_noise_digest(
    region: str = "LATAM",
    since: str = "2026-04-18",
    _api_key: str = Depends(verify_api_key),
) -> list[dict[str, Any]]:
    svc = NoiseBlockService()
    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid since date format") from exc
    digest = await svc.get_noise_digest(region_code=region, since=since_dt)
    return digest


@router.post("/noise/expire")
async def trigger_expire(
    _db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> ExpireResponse:
    from datetime import UTC, datetime
    svc = NoiseBlockService()
    count = await svc.expire_old_noise()
    return ExpireResponse(
        expired_count=count,
        timestamp=datetime.now(UTC).isoformat(),
    )
