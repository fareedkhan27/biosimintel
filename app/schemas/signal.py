from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.signal import Confidence, OperatingModelRelevance, SignalType


class GeoSignalBase(BaseModel):
    event_id: UUID | None = None
    competitor_id: UUID | None = None
    molecule_id: UUID
    region_id: UUID | None = None
    country_ids: list[UUID] = Field(default_factory=list)
    signal_type: SignalType
    confidence: Confidence
    relevance_score: int = Field(default=0, ge=0, le=100)
    department_tags: list[str] = Field(default_factory=list)
    operating_model_relevance: OperatingModelRelevance = OperatingModelRelevance.ALL
    delta_note: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    tier: int = Field(default=3, ge=1, le=3)
    expires_at: datetime | None = None


class GeoSignalCreate(GeoSignalBase):
    pass


class GeoSignalUpdate(BaseModel):
    event_id: UUID | None = None
    competitor_id: UUID | None = None
    molecule_id: UUID | None = None
    region_id: UUID | None = None
    country_ids: list[UUID] | None = None
    signal_type: SignalType | None = None
    confidence: Confidence | None = None
    relevance_score: int | None = Field(None, ge=0, le=100)
    department_tags: list[str] | None = None
    operating_model_relevance: OperatingModelRelevance | None = None
    delta_note: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    tier: int | None = Field(None, ge=1, le=3)
    expires_at: datetime | None = None


class GeoSignalRead(GeoSignalBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    competitor_name: str | None = None
    molecule_name: str | None = None
    region_name: str | None = None
    country_names: list[str] | None = None
    created_at: datetime
    updated_at: datetime
