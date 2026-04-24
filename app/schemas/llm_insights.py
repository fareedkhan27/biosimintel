from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InsightResult(BaseModel):
    """Guarded LLM insight result with metadata."""

    model_config = ConfigDict(from_attributes=True)

    executive_summary: str
    key_insights: list[str]
    recommended_actions: list[str]
    confidence: str
    model_used: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    from_cache: bool
    fallback: bool = False
    generated_at: datetime


class NarrativeRequest(BaseModel):
    """Request body for on-demand narrative generation."""

    molecule_id: UUID
    force_refresh: bool = False
