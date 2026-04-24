from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LaunchEstimate(BaseModel):
    """Single competitor-indication launch estimate."""

    model_config = ConfigDict(from_attributes=True)

    competitor_id: UUID
    competitor_name: str
    indication: str
    current_stage: str
    estimated_launch_date: date
    estimated_launch_quarter: str
    months_to_launch: int
    confidence_level: str
    velocity_multiplier: float
    events_last_90_days: int


class LaunchTimeline(BaseModel):
    """Full launch timeline for a molecule."""

    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    molecule_name: str
    estimates: list[LaunchEstimate]
    timeline_by_quarter: dict[str, list[LaunchEstimate]]
    imminent_threats: list[LaunchEstimate]
    pipeline_summary: dict[str, int]
    generated_at: datetime
