from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.intelligence_alerts import AlertReport
from app.services.intelligence_alerts import (
    detect_threshold_breaches,
    record_intelligence_baseline,
)

router = APIRouter(tags=["Intelligence Alerts"])


@router.get("/intelligence/alerts", response_model=AlertReport)
async def get_intelligence_alerts(
    molecule_id: UUID,
    min_severity: str = "low",
    db: AsyncSession = Depends(get_db),
) -> AlertReport:
    """Returns competitive intelligence alerts for a molecule."""
    report = await detect_threshold_breaches(molecule_id, db)
    if min_severity != "low":
        severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        min_level = severity_order.get(min_severity.lower(), 0)
        report.alerts = [
            a for a in report.alerts
            if severity_order.get(a.severity.lower(), 0) >= min_level
        ]
        report.critical_count = sum(1 for a in report.alerts if a.severity == "critical")
        report.high_count = sum(1 for a in report.alerts if a.severity == "high")
        report.has_critical = report.critical_count > 0
    return report


@router.post("/intelligence/alerts/baseline")
async def record_baseline(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record current intelligence state as baseline."""
    return await record_intelligence_baseline(molecule_id, db)
