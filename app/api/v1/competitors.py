from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.competitor import Competitor
from app.schemas.competitor import CompetitorCreate, CompetitorRead

router = APIRouter()


@router.get("", response_model=list[CompetitorRead])
async def list_competitors(
    molecule_id: UUID | None = Query(None),
    tier: int | None = Query(None, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
) -> list[Competitor]:
    """List competitors with filters."""
    stmt = select(Competitor)
    if molecule_id:
        stmt = stmt.where(Competitor.molecule_id == molecule_id)
    if tier is not None:
        stmt = stmt.where(Competitor.tier == tier)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CompetitorRead, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    payload: CompetitorCreate,
    db: AsyncSession = Depends(get_db),
) -> Competitor:
    """Create a competitor."""
    competitor = Competitor(**payload.model_dump())
    db.add(competitor)
    await db.commit()
    await db.refresh(competitor)
    return competitor


@router.get("/{competitor_id}", response_model=CompetitorRead)
async def get_competitor(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Competitor:
    """Get competitor profile."""
    result = await db.execute(select(Competitor).where(Competitor.id == competitor_id))
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise NotFoundException("Competitor")
    return competitor
