from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.event import EventRead


class IntelligenceSummary(BaseModel):
    molecule_id: UUID
    molecule_name: str
    total_events: int
    verified_events: int
    pending_events: int
    top_threats: list[EventRead]
    recent_events: list[EventRead]
    competitor_breakdown: dict[str, int]


class BriefingRequest(BaseModel):
    molecule_id: UUID
    departments: list[str] = Field(default_factory=list)
    since_days: int = 7


class BriefingSection(BaseModel):
    executive_summary: str
    market_sections: list[dict[str, Any]]
    milestones: list[dict[str, Any]]


class BriefingResponse(BaseModel):
    molecule_id: UUID
    departments: dict[str, BriefingSection]


class AskRequest(BaseModel):
    question: str
    molecule_id: UUID | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: float


class EmailBriefingRequest(BaseModel):
    molecule_id: UUID
    department: str = "market_access"
    format: str = "html"  # "html" or "json"
    since_days: int = 7
    bypass_preferences: bool = False
    recipients: list[EmailStr] | None = None


class BriefingTriggerRequest(BaseModel):
    molecule_id: UUID
    segments: list[str] = Field(default_factory=lambda: ["market_access"])
    since_days: int = 30
    recipient: EmailStr = "na-team@biosimintel.com"


class EmailBriefingResponse(BaseModel):
    html: str | None = None
    json_payload: dict[str, Any] | None = None
    subject: str
    recipient: str
    cc: str | None = None
    from_email: str
    event_count: int
    region: str | None = None
