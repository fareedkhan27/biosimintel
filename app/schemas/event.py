from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    molecule_id: UUID
    source_document_id: UUID | None = None
    competitor_id: UUID | None = None
    event_type: str = Field(..., max_length=50)
    event_subtype: str | None = Field(None, max_length=50)
    development_stage: str | None = Field(None, max_length=50)
    indication: str | None = Field(None, max_length=100)
    indication_priority: str | None = Field(None, max_length=10)
    is_pivotal_indication: bool = False
    extrapolation_targets: list[str] = Field(default_factory=list)
    country: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=50)
    event_date: datetime | None = None
    announced_date: datetime | None = None
    summary: str | None = None
    evidence_excerpt: str | None = None
    threat_score: int | None = Field(None, ge=0, le=100)
    traffic_light: str | None = Field(None, max_length=10)
    score_breakdown: dict[str, Any] | None = None
    verification_status: str = Field(default="pending", max_length=20)
    verification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verified_sources_count: int = 0
    review_status: str = Field(default="pending", max_length=20)
    ai_summary: str | None = None
    ai_why_it_matters: str | None = None
    ai_recommended_action: str | None = None
    ai_confidence_note: str | None = None
    ai_interpreted_at: datetime | None = None


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class EventListParams(BaseModel):
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    event_type: str | None = None
    traffic_light: str | None = None
    indication: str | None = None
    country: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    skip: int = 0
    limit: int = 100
