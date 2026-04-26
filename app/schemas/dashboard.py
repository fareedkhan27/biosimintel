from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ThreatLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "MONITORING"]
SourceStatus = Literal["ACTIVE", "DORMANT"]


class HeatmapCountry(BaseModel):
    country_code: str = Field(..., max_length=2)
    country_name: str = Field(..., max_length=100)
    region: str = Field(..., max_length=50)
    highest_competitor_threat_score: int
    threat_level: ThreatLevel
    top_competitor_name: str = Field(..., max_length=100)
    signal_count_7d: int
    signal_count_30d: int


class TimelineSignal(BaseModel):
    id: str
    title: str
    tier: int
    source_type: str | None
    country_name: str
    country_count: int
    country_codes: list[str] = Field(default_factory=list)
    competitor_name: str
    created_at: datetime
    url: str | None
    event_date: datetime | None = None


class CompetitorDashboard(BaseModel):
    id: UUID
    name: str = Field(..., max_length=100)
    watch_list: bool
    molecules: list[str]
    active_countries_count: int
    country_codes: list[str] = Field(default_factory=list)
    latest_signal_date: datetime | None
    latest_signal_date_formatted: str | None = None
    latest_signal_title: str | None
    total_signals_count: int


class SourceHealth(BaseModel):
    source_name: str
    status: SourceStatus
    last_poll_timestamp: datetime | None
    signal_count_total: int
    signal_count_7d: int


class RegionDashboard(BaseModel):
    region_code: str
    country_count: int
    total_signals_7d: int
    total_signals_30d: int
    avg_threat_score: float
    avg_threat_rationale: str
    top_country_by_threat: str
    top_country_rationale: str
    top_competitor_by_presence: str
    top_competitor_rationale: str
    calculation_note: str
