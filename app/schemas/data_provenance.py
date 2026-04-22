from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataProvenanceBase(BaseModel):
    event_id: UUID
    source_document_id: UUID
    field_name: str = Field(..., max_length=100)
    raw_value: str | None = None
    normalized_value: str | None = None
    extraction_method: str = Field(..., max_length=50)
    extractor_version: str | None = Field(None, max_length=20)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified_by: str | None = Field(None, max_length=50)
    verification_timestamp: datetime | None = None


class DataProvenanceCreate(DataProvenanceBase):
    pass


class DataProvenanceRead(DataProvenanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
