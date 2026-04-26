from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PressReleaseRawBase(BaseModel):
    source_name: str
    source_url: str
    feed_type: str = "MANUAL"
    article_title: str
    article_summary: str | None = None
    article_content: str | None = None
    published_date: date | None = None
    author: str | None = None


class PressReleaseRawCreate(PressReleaseRawBase):
    pass


class PressReleaseRawResponse(PressReleaseRawBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    signal_type: str | None = None
    auto_verified: bool
    created_at: datetime
    molecule_name: str | None = None
    competitor_name: str | None = None


class PressReleaseIngestResult(BaseModel):
    ingestion_id: UUID
    status: str
    signal_created: bool
    signal_id: UUID | None = None
    noise_created: bool
    classification: str
    confidence: int
