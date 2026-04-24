from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertEvent(BaseModel):
    """Single competitive intelligence alert."""

    model_config = ConfigDict(from_attributes=True)

    alert_type: str
    severity: str
    title: str
    description: str
    competitor_name: str | None
    indication: str | None
    old_value: str | None
    new_value: str | None
    detected_at: datetime


class AlertReport(BaseModel):
    """Aggregated alert report for a molecule."""

    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    molecule_name: str
    alerts: list[AlertEvent]
    critical_count: int
    high_count: int
    has_critical: bool
    generated_at: datetime
