from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmaEparRawPollBase(BaseModel):
    poll_date: date
    endpoint_url: str
    status: str = "success"
    error_message: str | None = None


class EmaEparRawPollCreate(EmaEparRawPollBase):
    raw_json: dict[str, Any] = Field(default_factory=dict)


class EmaEparRawPollResponse(EmaEparRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_json: dict[str, Any]
    created_at: datetime


class EmaEparEntryBase(BaseModel):
    product_name: str
    active_substance: str
    marketing_authorisation_holder: str
    authorisation_status: str
    indication: str | None = None
    decision_date: date | None = None
    epar_url: str
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    is_relevant: bool = False


class EmaEparEntryCreate(EmaEparEntryBase):
    raw_poll_id: UUID


class EmaEparEntryResponse(EmaEparEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class EmaEparPollResult(BaseModel):
    poll_id: UUID
    poll_date: date
    status: str
    new_entries: int
    relevant_entries: int
    signals_created: int
