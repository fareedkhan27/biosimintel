from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.molecule import Molecule
from app.schemas.molecule import MoleculeCreate, MoleculeRead, MoleculeUpdate

router = APIRouter()


@router.get("", response_model=list[MoleculeRead])
async def list_molecules(db: AsyncSession = Depends(get_db)) -> list[Molecule]:
    """List all molecules."""
    result = await db.execute(select(Molecule))
    return list(result.scalars().all())


@router.post("", response_model=MoleculeRead, status_code=status.HTTP_201_CREATED)
async def create_molecule(
    payload: MoleculeCreate,
    db: AsyncSession = Depends(get_db),
) -> Molecule:
    """Create a new molecule config."""
    molecule = Molecule(**payload.model_dump())
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
