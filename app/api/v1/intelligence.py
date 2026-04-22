from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.event import Event
from app.models.molecule import Molecule
from app.schemas.event import EventRead
from app.schemas.intelligence import (
    AskRequest,
    AskResponse,
    BriefingRequest,
    BriefingResponse,
    EmailBriefingRequest,
    EmailBriefingResponse,
    IntelligenceSummary,
)

router = APIRouter()


@router.get("/summary", response_model=IntelligenceSummary)
async def intelligence_summary(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> IntelligenceSummary:
    """Dashboard summary for molecule."""
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    events_result = await db.execute(
        select(Event).options(selectinload(Event.competitor)).where(Event.molecule_id == molecule_id)
    )
    events = list(events_result.scalars().all())

    verified = [e for e in events if e.verification_status == "verified"]
    pending = [e for e in events if e.verification_status == "pending"]

    top_threats = sorted(
        [e for e in events if e.threat_score is not None],
        key=lambda x: x.threat_score or 0,
        reverse=True,
    )[:5]

    recent_events = sorted(events, key=lambda x: x.created_at, reverse=True)[:5]

    competitor_breakdown: dict[str, int] = {}
    for e in events:
        name = e.competitor.canonical_name if e.competitor else "Unknown"
        competitor_breakdown[name] = competitor_breakdown.get(name, 0) + 1

    return IntelligenceSummary(
        molecule_id=molecule_id,
        molecule_name=str(molecule.molecule_name),
        total_events=len(events),
        verified_events=len(verified),
        pending_events=len(pending),
        top_threats=[EventRead.model_validate(e) for e in top_threats],
        recent_events=[EventRead.model_validate(e) for e in recent_events],
        competitor_breakdown=competitor_breakdown,
    )


@router.get("/top-threats", response_model=list[EventRead])
async def top_threats(
    molecule_id: UUID,
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[Event]:
    """Highest threat_score events."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.competitor))
        .where(Event.molecule_id == molecule_id)
        .where(Event.verification_status == "verified")
        .order_by(Event.threat_score.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/recent", response_model=list[EventRead])
async def recent_events(
    molecule_id: UUID,
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[Event]:
    """Most recent verified events."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.competitor))
        .where(Event.molecule_id == molecule_id)
        .where(Event.verification_status == "verified")
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/briefing", response_model=BriefingResponse)
async def generate_briefing(
    payload: BriefingRequest,
    db: AsyncSession = Depends(get_db),
) -> BriefingResponse:
    """Generate department briefing."""
    from app.services.intelligence_service import IntelligenceService
    service = IntelligenceService()
    return await service.generate_briefing(payload, db)


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    payload: AskRequest,
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    """Natural language Q&A."""
    from app.services.ai.qa_engine import QAEngine
    engine = QAEngine()
    return await engine.answer(payload, db)


@router.post("/briefing/email", response_model=EmailBriefingResponse)
async def generate_email_briefing(
    payload: EmailBriefingRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailBriefingResponse:
    """Generate email-ready department briefing (HTML or JSON)."""
    from app.services.intelligence_service import IntelligenceService
    service = IntelligenceService()
    return await service.generate_email_briefing(payload, db)
