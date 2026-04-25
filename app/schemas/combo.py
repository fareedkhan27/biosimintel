from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.combo import ComboCapability


class MoleculePairBase(BaseModel):
    primary_molecule_id: UUID
    secondary_molecule_id: UUID
    combo_name: str = Field(..., max_length=100)
    is_active: bool = True


class MoleculePairCreate(MoleculePairBase):
    pass


class MoleculePairUpdate(BaseModel):
    primary_molecule_id: UUID | None = None
    secondary_molecule_id: UUID | None = None
    combo_name: str | None = Field(None, max_length=100)
    is_active: bool | None = None


class MoleculePairRead(MoleculePairBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class CompetitorMoleculeAssignmentBase(BaseModel):
    competitor_id: UUID
    molecule_id: UUID
    asset_name: str = Field(..., max_length=100)
    development_stage: str | None = Field(None, max_length=50)
    is_primary_focus: bool = False
    combo_capability: ComboCapability
    has_clinical_trial_for_combo: bool = False
    notes: str | None = None


class CompetitorMoleculeAssignmentCreate(CompetitorMoleculeAssignmentBase):
    pass


class CompetitorMoleculeAssignmentUpdate(BaseModel):
    competitor_id: UUID | None = None
    molecule_id: UUID | None = None
    asset_name: str | None = Field(None, max_length=100)
    development_stage: str | None = Field(None, max_length=50)
    is_primary_focus: bool | None = None
    combo_capability: ComboCapability | None = None
    has_clinical_trial_for_combo: bool | None = None
    notes: str | None = None


class CompetitorMoleculeAssignmentRead(CompetitorMoleculeAssignmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
