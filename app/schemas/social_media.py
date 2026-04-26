from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SocialMediaRawBase(BaseModel):
    source_platform: str
    post_url: str
    author: str | None = None
    post_text: str
    published_date: date | None = None
    engagement_score: int | None = None
    matched_keywords: str | None = None


class SocialMediaRawCreate(SocialMediaRawBase):
    pass


class SocialMediaRawResponse(SocialMediaRawBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    noise_signal_id: UUID | None = None
    created_at: datetime
    molecule_name: str | None = None
    competitor_name: str | None = None


class SocialMediaIngestResult(BaseModel):
    ingestion_id: UUID
    noise_created: bool
    noise_signal_id: UUID
    confidence: int
    message: str


class SocialMediaStats(BaseModel):
    total_ingested: int
    total_verified: int
    total_dismissed: int
    total_expired: int
    by_platform: dict[str, int]
