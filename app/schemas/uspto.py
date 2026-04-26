from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsptoRawPollBase(BaseModel):
    poll_date: date
    search_query: str
    total_count: int | None = None
    status: str = "success"
    error_message: str | None = None


class UsptoRawPollCreate(UsptoRawPollBase):
    raw_json: dict[str, Any] = Field(default_factory=dict)


class UsptoRawPollResponse(UsptoRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_json: dict[str, Any]
    created_at: datetime


class UsptoEntryBase(BaseModel):
    patent_number: str
    title: str
    abstract: str | None = None
    assignee: str | None = None
    inventors: str | None = None
    filing_date: date | None = None
    grant_date: date | None = None
    expiry_date: date | None = None
    patent_url: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    patent_type: str = "GENERAL"
    is_relevant: bool = False


class UsptoEntryCreate(UsptoEntryBase):
    raw_poll_id: UUID


class UsptoEntryResponse(UsptoEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class UsptoPollResult(BaseModel):
    poll_id: UUID
    poll_date: date
    status: str
    total_found: int
    new_entries: int
    relevant_entries: int
    signals_created: int
