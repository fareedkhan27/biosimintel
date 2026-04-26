from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EpoRawPollBase(BaseModel):
    poll_date: date
    search_query: str
    total_count: int | None = None
    status: str = "success"
    error_message: str | None = None


class EpoRawPollCreate(EpoRawPollBase):
    raw_xml: str | None = None


class EpoRawPollResponse(EpoRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_xml: str | None = None
    created_at: datetime


class EpoEntryBase(BaseModel):
    epo_publication_number: str
    title: str
    abstract: str | None = None
    applicant: str | None = None
    inventors: str | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    patent_status: str | None = None
    epo_url: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    patent_type: str = "GENERAL"
    is_relevant: bool = False


class EpoEntryCreate(EpoEntryBase):
    raw_poll_id: UUID


class EpoEntryResponse(EpoEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class EpoPollResult(BaseModel):
    poll_id: UUID
    poll_date: date
    status: str
    total_found: int
    new_entries: int
    relevant_entries: int
    signals_created: int
