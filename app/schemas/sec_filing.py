from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SecFilingBase(BaseModel):
    form_type: str
    filing_date: datetime
    accession_number: str
    primary_doc_url: str
    title: str | None


class SecFilingCreate(SecFilingBase):
    competitor_id: UUID
    cik: str


class SecFilingResponse(SecFilingBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    competitor_id: UUID
    cik: str
    fetched_at: datetime
