from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PubmedRawPollBase(BaseModel):
    poll_date: date
    search_query: str
    total_count: int | None = None
    status: str = "success"
    error_message: str | None = None


class PubmedRawPollCreate(PubmedRawPollBase):
    raw_json: dict[str, Any] = Field(default_factory=dict)


class PubmedRawPollResponse(PubmedRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_json: dict[str, Any]
    created_at: datetime


class PubmedEntryBase(BaseModel):
    pmid: str
    doi: str | None = None
    title: str
    abstract: str | None = None
    authors: str | None = None
    journal: str | None = None
    pub_date: date | None = None
    article_url: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    publication_type: str = "GENERAL"
    is_relevant: bool = False


class PubmedEntryCreate(PubmedEntryBase):
    raw_poll_id: UUID


class PubmedEntryResponse(PubmedEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class PubmedPollResult(BaseModel):
    poll_id: UUID
    poll_date: date
    status: str
    total_found: int
    new_entries: int
    relevant_entries: int
    signals_created: int
