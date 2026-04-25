from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailRegionFilter,
    EmailRole,
)


class EmailPreferenceBase(BaseModel):
    user_email: str = Field(..., max_length=200)
    user_name: str = Field(..., max_length=200)
    role: EmailRole
    region_filter: EmailRegionFilter
    department_filter: EmailDepartmentFilter
    operating_model_threshold: EmailOperatingModelThreshold = EmailOperatingModelThreshold.ALL
    is_active: bool = True


class EmailPreferenceCreate(EmailPreferenceBase):
    pass


class EmailPreferenceUpdate(BaseModel):
    user_email: str | None = Field(None, max_length=200)
    user_name: str | None = Field(None, max_length=200)
    role: EmailRole | None = None
    region_filter: EmailRegionFilter | None = None
    department_filter: EmailDepartmentFilter | None = None
    operating_model_threshold: EmailOperatingModelThreshold | None = None
    is_active: bool | None = None


class EmailPreferenceRead(EmailPreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
