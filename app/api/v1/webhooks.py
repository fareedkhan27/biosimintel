from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.event import Event
from app.schemas.event import EventRead

router = APIRouter()


def _resolve_region_email(country: str | None, region: str | None) -> str:
    """Map event geography to regional email distribution."""
    routing: dict[str, str] = {
        "india": settings.APAC_EMAIL,
        "united states": settings.NA_EMAIL,
        "us": settings.NA_EMAIL,
        "european union": settings.EMEA_EMAIL,
        "eu": settings.EMEA_EMAIL,
        "germany": settings.EMEA_EMAIL,
        "france": settings.EMEA_EMAIL,
        "uk": settings.EMEA_EMAIL,
        "united kingdom": settings.EMEA_EMAIL,
        "spain": settings.EMEA_EMAIL,
        "italy": settings.EMEA_EMAIL,
        "japan": settings.APAC_EMAIL,
        "china": settings.APAC_EMAIL,
        "australia": settings.APAC_EMAIL,
    }
    for key in [country, region]:
        if key:
            normalized = key.lower().strip()
            if normalized in routing:
                return routing[normalized]
    return settings.EXECUTIVE_EMAIL


@router.post("/red-alert", response_model=dict[str, Any])
async def red_alert_webhook(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Check for verified Red events in the last 24 hours. Called by n8n."""
    since = datetime.now(UTC) - timedelta(hours=24)

    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.competitor))
        .where(Event.verification_status == "verified")
        .where(Event.traffic_light == "Red")
        .where(Event.created_at >= since)
        .order_by(Event.threat_score.desc())
    )
    events = list(events_result.scalars().all())

    alerts: list[dict[str, Any]] = []
    for event in events:
        region_email = _resolve_region_email(event.country, event.region)  # type: ignore[arg-type]
        alerts.append({
            "event": EventRead.model_validate(event),
            "routing": {
                "recipient": region_email,
                "from_email": settings.DEFAULT_FROM_EMAIL,
                "region": event.country or event.region or "Global",
            },
        })

    return {
        "alert_count": len(alerts),
        "alerts": alerts,
        "checked_since": since.isoformat(),
    }
