from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitorBase(BaseModel):
    canonical_name: str = Field(..., max_length=100)
    tier: int = Field(..., ge=1, le=4)
    asset_code: str | None = Field(None, max_length=50)
    development_stage: str | None = Field(None, max_length=50)
    status: str | None = Field(None, max_length=50)
    primary_markets: list[str] = Field(default_factory=list)
    launch_window: str | None = Field(None, max_length=50)
    price_position: str | None = Field(None, max_length=100)
    parent_company: str | None = Field(None, max_length=100)
    partnership_status: str | None = Field(None, max_length=100)
    cik: str | None = Field(None, max_length=10)


class CompetitorCreate(CompetitorBase):
    molecule_id: UUID


class CompetitorRead(CompetitorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID
    created_at: datetime
