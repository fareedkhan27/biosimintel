from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.noise import NoiseSourceType, NoiseVerificationStatus


class NoiseSignalBase(BaseModel):
    geo_signal_id: UUID | None = None
    raw_text: str
    source_type: NoiseSourceType
    source_url: str | None = None
    source_author: str | None = Field(None, max_length=100)
    expires_at: datetime | None = None
    verification_notes: str | None = None


class NoiseSignalCreate(NoiseSignalBase):
    pass


class NoiseSignalUpdate(BaseModel):
    geo_signal_id: UUID | None = None
    raw_text: str | None = None
    source_type: NoiseSourceType | None = None
    source_url: str | None = None
    source_author: str | None = Field(None, max_length=100)
    verification_status: NoiseVerificationStatus | None = None
    verified_at: datetime | None = None
    verified_by: str | None = Field(None, max_length=100)
    dismissed_at: datetime | None = None
    dismissed_by: str | None = Field(None, max_length=100)
    expires_at: datetime | None = None
    verification_notes: str | None = None
    escalation_count: int | None = None


class NoiseSignalRead(NoiseSignalBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    flagged_at: datetime
    verification_status: NoiseVerificationStatus
    verified_at: datetime | None = None
    verified_by: str | None = None
    dismissed_at: datetime | None = None
    dismissed_by: str | None = None
    escalation_count: int = 0
