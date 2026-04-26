from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EuCtisRawScrapeBase(BaseModel):
    scrape_date: date
    portal_url: str
    search_query: str
    total_results: int | None = None
    raw_html: str | None = None
    status: str = "success"
    error_message: str | None = None


class EuCtisRawScrapeCreate(EuCtisRawScrapeBase):
    pass


class EuCtisRawScrapeResponse(EuCtisRawScrapeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class EuCtisEntryBase(BaseModel):
    ctis_number: str
    sponsor_name: str | None = None
    trial_title: str
    intervention: str | None = None
    condition: str | None = None
    phase: str | None = None
    status: str | None = None
    eu_member_state: str | None = None
    decision_date: date | None = None
    ctis_url: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    is_relevant: bool = False


class EuCtisEntryCreate(EuCtisEntryBase):
    raw_scrape_id: UUID


class EuCtisEntryResponse(EuCtisEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_scrape_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class EuCtisScrapeResult(BaseModel):
    scrape_id: UUID
    scrape_date: date
    status: str
    total_results: int
    new_entries: int
    relevant_entries: int
    signals_created: int
