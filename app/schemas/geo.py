from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.geo import OperatingModel, RegionCode


class RegionBase(BaseModel):
    name: str = Field(..., max_length=100)
    code: RegionCode


class RegionCreate(RegionBase):
    pass


class RegionUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    code: RegionCode | None = None


class RegionRead(RegionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class CountryBase(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=2)
    region_id: UUID
    operating_model: OperatingModel
    local_regulatory_agency_name: str | None = Field(None, max_length=100)
    local_currency_code: str | None = Field(None, max_length=3)
    ema_parallel_recognition: bool = False
    is_active: bool = True


class CountryCreate(CountryBase):
    pass


class CountryUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    code: str | None = Field(None, max_length=2)
    region_id: UUID | None = None
    operating_model: OperatingModel | None = None
    local_regulatory_agency_name: str | None = Field(None, max_length=100)
    local_currency_code: str | None = Field(None, max_length=3)
    ema_parallel_recognition: bool | None = None
    is_active: bool | None = None


class CountryRead(CountryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class CompetitorCapabilityBase(BaseModel):
    competitor_id: UUID
    region_id: UUID
    has_local_manufacturing: bool = False
    has_local_regulatory_filing: bool = False
    has_local_commercial_infrastructure: bool = False
    local_partner_name: str | None = Field(None, max_length=100)
    confidence_score: int = Field(default=0, ge=0, le=100)
    assessed_at: datetime | None = None
    source_notes: str | None = None


class CompetitorCapabilityCreate(CompetitorCapabilityBase):
    pass


class CompetitorCapabilityUpdate(BaseModel):
    competitor_id: UUID | None = None
    region_id: UUID | None = None
    has_local_manufacturing: bool | None = None
    has_local_regulatory_filing: bool | None = None
    has_local_commercial_infrastructure: bool | None = None
    local_partner_name: str | None = Field(None, max_length=100)
    confidence_score: int | None = Field(None, ge=0, le=100)
    assessed_at: datetime | None = None
    source_notes: str | None = None


class CompetitorCapabilityRead(CompetitorCapabilityBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
