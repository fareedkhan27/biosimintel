from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OpenfdaRawPollBase(BaseModel):
    poll_date: date
    endpoint_url: str
    status: str = "success"
    error_message: str | None = None


class OpenfdaRawPollCreate(OpenfdaRawPollBase):
    query_params: dict[str, Any] | None = Field(default_factory=dict)
    raw_json: dict[str, Any] = Field(default_factory=dict)


class OpenfdaRawPollResponse(OpenfdaRawPollBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_params: dict[str, Any] | None
    raw_json: dict[str, Any]
    created_at: datetime


class OpenfdaEntryBase(BaseModel):
    application_number: str | None = None
    brand_name: str | None = None
    generic_name: str | None = None
    manufacturer_name: str | None = None
    product_type: str | None = None
    submission_type: str | None = None
    submission_status: str | None = None
    approval_date: date | None = None
    openfda_url: str | None = None
    molecule_id: UUID | None = None
    competitor_id: UUID | None = None
    is_relevant: bool = False


class OpenfdaEntryCreate(OpenfdaEntryBase):
    raw_poll_id: UUID


class OpenfdaEntryResponse(OpenfdaEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_poll_id: UUID
    molecule_name: str | None = None
    competitor_name: str | None = None
    created_at: datetime


class OpenfdaPollResult(BaseModel):
    poll_id: UUID
    poll_date: date
    status: str
    new_entries: int
    relevant_entries: int
    signals_created: int
