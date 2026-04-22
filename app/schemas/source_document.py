from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceDocumentBase(BaseModel):
    source_name: str = Field(..., max_length=50)
    source_type: str = Field(..., max_length=50)
    external_id: str | None = Field(None, max_length=200)
    title: str | None = None
    url: str
    published_at: datetime | None = None
    raw_payload: dict[str, Any] | None = None
    raw_text: str | None = None
    content_hash: str | None = Field(None, max_length=64)
    processing_status: str = Field(default="pending", max_length=20)
    molecule_id: UUID | None = None


class SourceDocumentCreate(SourceDocumentBase):
    pass


class SourceDocumentRead(SourceDocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fetched_at: datetime
    created_at: datetime
