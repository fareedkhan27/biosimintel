from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.db.session import get_db
from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailPreference,
    EmailRegionFilter,
    EmailRole,
)
from app.services.email_v2_service import EmailV2Service

router = APIRouter()


class DailyPulseRequest(BaseModel):
    preference_id: UUID | None = None
    region: str = Field(default="LATAM", max_length=20)
    department: str = Field(default="commercial", max_length=20)
    role: str = Field(default="commercial", max_length=20)


class WeeklyStrategicRequest(BaseModel):
    preference_id: UUID | None = None
    region: str = Field(default="CEE_EU", max_length=20)
    department: str = Field(default="market_access", max_length=20)
    role: str = Field(default="market_access", max_length=20)


class GmSummaryRequest(BaseModel):
    preference_id: UUID | None = None


def _build_preference_from_params(
    region: str, department: str, role: str
) -> EmailPreference:
    """Construct a temporary EmailPreference from query/body params."""
    try:
        region_enum = EmailRegionFilter(region.lower())
    except ValueError:
        region_enum = EmailRegionFilter.ALL

    try:
        dept_enum = EmailDepartmentFilter(department.lower())
    except ValueError:
        dept_enum = EmailDepartmentFilter.ALL

    try:
        role_enum = EmailRole(role.lower())
    except ValueError:
        role_enum = EmailRole.COMMERCIAL

    return EmailPreference(
        user_email="temp@biosimintel.com",
        user_name="Temp User",
        role=role_enum,
        region_filter=region_enum,
        department_filter=dept_enum,
        operating_model_threshold=EmailOperatingModelThreshold.ALL,
        is_active=True,
    )


async def _resolve_preference(
    db: AsyncSession,
    preference_id: UUID | None,
    region: str,
    department: str,
    role: str,
) -> EmailPreference:
    if preference_id:
        result = await db.execute(
            select(EmailPreference).where(EmailPreference.id == preference_id)
        )
        pref = result.scalar_one_or_none()
        if pref:
            return pref
        raise HTTPException(status_code=404, detail="Email preference not found")
    return _build_preference_from_params(region, department, role)


@router.post("/daily-pulse")
async def post_daily_pulse(
    request: DailyPulseRequest,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> str:
    pref = await _resolve_preference(
        db, request.preference_id, request.region, request.department, request.role
    )
    since = datetime.now(UTC) - timedelta(days=1)
    svc = EmailV2Service()
    return await svc.compose_daily_pulse(pref, since)


@router.get("/daily-pulse")
async def get_daily_pulse(
    region: str = Query(default="LATAM"),
    department: str = Query(default="commercial"),
    role: str = Query(default="commercial"),
    _api_key: str = Depends(verify_api_key),
) -> str:
    pref = _build_preference_from_params(region, department, role)
    since = datetime.now(UTC) - timedelta(days=1)
    svc = EmailV2Service()
    return await svc.compose_daily_pulse(pref, since)


@router.post("/weekly-strategic")
async def post_weekly_strategic(
    request: WeeklyStrategicRequest,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> str:
    pref = await _resolve_preference(
        db, request.preference_id, request.region, request.department, request.role
    )
    svc = EmailV2Service()
    return await svc.compose_weekly_strategic(pref)


@router.get("/weekly-strategic")
async def get_weekly_strategic(
    region: str = Query(default="CEE_EU"),
    department: str = Query(default="market_access"),
    role: str = Query(default="market_access"),
    _api_key: str = Depends(verify_api_key),
) -> str:
    pref = _build_preference_from_params(region, department, role)
    svc = EmailV2Service()
    return await svc.compose_weekly_strategic(pref)


@router.post("/gm-summary")
async def post_gm_summary(
    request: GmSummaryRequest,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> str:
    if request.preference_id:
        await _resolve_preference(
            db, request.preference_id, "ALL", "ALL", "gm"
        )
    svc = EmailV2Service()
    return await svc.compose_gm_summary()


@router.get("/gm-summary")
async def get_gm_summary(
    _api_key: str = Depends(verify_api_key),
) -> str:
    svc = EmailV2Service()
    return await svc.compose_gm_summary()
