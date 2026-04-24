"""Pydantic schemas for the Competitive Indication Landscape (heatmap) module."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HeatmapCell(BaseModel):
    """A single cell in the indication x competitor matrix."""

    model_config = ConfigDict(from_attributes=True)

    competitor_id: UUID
    indication: str
    event_count: int
    avg_threat_score: float
    max_threat_score: int
    latest_stage: str
    latest_event_date: datetime
    heat_score: int
    stage_abbreviation: str


class CompetitorColumn(BaseModel):
    """Metadata for a competitor displayed as a column in the heatmap."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cik: str | None
    breadth_score: int
    depth_score: int
    focus_type: str


class IndicationLandscape(BaseModel):
    """Full competitive indication landscape for a molecule."""

    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    molecule_name: str
    indications: list[str]
    competitors: list[CompetitorColumn]
    matrix: list[list[HeatmapCell | None]]
    white_space_indications: list[str]
    contested_indications: list[str]
    vulnerability_index: int
    generated_at: datetime
    total_events_analyzed: int
