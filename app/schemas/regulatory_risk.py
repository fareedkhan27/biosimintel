from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PatentCliffEntry(BaseModel):
    """Patent cliff data enriched with proximity scoring."""

    model_config = ConfigDict(from_attributes=True)

    indication: str
    patent_type: str
    patent_number: str | None
    expiry_date: date
    territory: str
    days_to_expiry: int
    cliff_score: int
    competitors_active: bool


class RegulatoryRiskProfile(BaseModel):
    """Regulatory risk and patent overlay for a molecule."""

    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    patent_cliffs: list[PatentCliffEntry]
    pathway_weights: dict[str, float]
    generated_at: datetime
