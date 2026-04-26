from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WhoIctrpRawPollBase(BaseModel):
    poll_month: str
    download_url: str
    csv_filename: str | None = None
    total_rows: int | None = None
    filtered_rows: int | None = None
    status: str = "success"
    error_message: str | None = None


class WhoIctrpRawPollCreate(WhoIctrpRawPollBase):
    pass


class WhoIctrpRawPollResponse(WhoIctrpRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class WhoIctrpEntryBase(BaseModel):
    trial_id: str
    reg_id: str | None = None
    public_title: str
    scientific_title: str | None = None
    intervention: str | None = None
    condition: str | None = None
    recruitment_status: str | None = None
    phase: str | None = None
    study_type: str | None = None
    date_registration: date | None = None
    date_enrolment: date | None = None
    countries: str | None = None
    source_register: str | None = None
    url: str | None = None
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    is_relevant: bool = False


class WhoIctrpEntryCreate(WhoIctrpEntryBase):
    raw_poll_id: UUID


class WhoIctrpEntryResponse(WhoIctrpEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class WhoIctrpPollResult(BaseModel):
    poll_id: UUID
    poll_month: str
    status: str
    total_rows: int
    filtered_rows: int
    relevant_entries: int
    signals_created: int
