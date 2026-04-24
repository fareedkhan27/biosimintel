from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_api_key
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.molecule import Molecule
from app.schemas.molecule import (
    MoleculeBriefingPreference,
    MoleculeCreate,
    MoleculeRead,
    MoleculeUpdate,
)

router = APIRouter()


@router.get("", response_model=list[MoleculeRead])
async def list_molecules(
    briefing_mode: str | None = Query(None, description="Filter by briefing mode (weekly_digest, silent, alert_only, on_demand)"),
    db: AsyncSession = Depends(get_db),
) -> list[Molecule]:
    """List all molecules. Optionally filter by briefing_mode."""
    stmt = select(Molecule)
    if briefing_mode is not None:
        stmt = stmt.where(Molecule.briefing_mode == briefing_mode).where(Molecule.is_monitored.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=MoleculeRead, status_code=status.HTTP_201_CREATED)
async def create_molecule(
    payload: MoleculeCreate,
    db: AsyncSession = Depends(get_db),
) -> Molecule:
    """Create a new molecule config. New molecules default to silent mode."""
    data = payload.model_dump()
    data.setdefault("briefing_mode", "silent")
    data.setdefault("alert_threshold", 60)
    data.setdefault("is_monitored", True)
    molecule = Molecule(**data)
    db.add(molecule)
    await db.commit()
    await db.refresh(molecule)
    return molecule


@router.get("/{molecule_id}", response_model=MoleculeRead)
async def get_molecule(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Molecule:
    """Get molecule with full config."""
    result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")
    return molecule


@router.patch("/{molecule_id}", response_model=MoleculeRead)
async def update_molecule(
    molecule_id: UUID,
    payload: MoleculeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Molecule:
    """Update molecule config."""
    result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(molecule, field, value)

    await db.commit()
    await db.refresh(molecule)
    return molecule


@router.patch("/{molecule_id}/preferences", response_model=MoleculeRead)
async def update_molecule_preferences(
    molecule_id: UUID,
    prefs: MoleculeBriefingPreference,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> Molecule:
    """Update briefing preference controls for a molecule."""
    result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    molecule.briefing_mode = prefs.briefing_mode  # type: ignore[assignment]
    molecule.alert_threshold = prefs.alert_threshold  # type: ignore[assignment]
    molecule.is_monitored = prefs.is_monitored  # type: ignore[assignment]

    await db.commit()
    await db.refresh(molecule)
    return molecule
