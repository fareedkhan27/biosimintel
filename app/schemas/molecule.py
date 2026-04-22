from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MoleculeBase(BaseModel):
    molecule_name: str = Field(..., max_length=100)
    reference_brand: str = Field(..., max_length=100)
    manufacturer: str = Field(..., max_length=100)
    search_terms: list[str] = Field(default_factory=list)
    indications: dict[str, Any] = Field(default_factory=dict)
    loe_timeline: dict[str, Any] = Field(default_factory=dict)
    competitor_universe: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class MoleculeCreate(MoleculeBase):
    pass


class MoleculeUpdate(BaseModel):
    molecule_name: str | None = Field(None, max_length=100)
    reference_brand: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=100)
    search_terms: list[str] | None = None
    indications: dict[str, Any] | None = None
    loe_timeline: dict[str, Any] | None = None
    competitor_universe: list[str] | None = None
    scoring_weights: dict[str, Any] | None = None
    is_active: bool | None = None


class MoleculeRead(MoleculeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
