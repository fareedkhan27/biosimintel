from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import verify_api_key
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
    BriefingTriggerRequest,
    EmailBriefingRequest,
    EmailBriefingResponse,
    IntelligenceSummary,
)
from app.schemas.llm_insights import InsightResult

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


@router.get("/narrative", response_model=InsightResult)
async def get_executive_narrative(
    molecule_id: UUID,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
) -> InsightResult:
    """Generate AI-powered executive narrative for a molecule."""
    from app.services.llm_insights import generate_executive_narrative
    return await generate_executive_narrative(molecule_id, db, force_refresh=force_refresh)


@router.post("/briefing/email", response_model=EmailBriefingResponse)
async def generate_email_briefing(
    payload: EmailBriefingRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailBriefingResponse:
    """Generate email-ready department briefing (HTML or JSON)."""
    from app.services.intelligence_service import IntelligenceService

    molecule_result = await db.execute(select(Molecule).where(Molecule.id == payload.molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    # For auto-generated briefings (not on-demand), respect preferences
    if not payload.bypass_preferences:
        if molecule.briefing_mode == "silent":
            raise HTTPException(status_code=403, detail="Molecule is in silent mode")
        if molecule.briefing_mode == "on_demand":
            raise HTTPException(
                status_code=403,
                detail="Molecule is in on-demand mode — use /briefing/trigger",
            )
        if molecule.briefing_mode == "alert_only":
            # This shouldn't be hit by the weekly workflow, but guard anyway
            raise HTTPException(status_code=403, detail="Molecule is in alert-only mode")

    service = IntelligenceService()
    response = await service.generate_email_briefing(payload, db)

    # Update last_briefing_sent_at for successful auto-generated sends
    if not payload.bypass_preferences:
        molecule.last_briefing_sent_at = datetime.now(UTC)  # type: ignore[assignment]
        await db.commit()

    return response


@router.post("/briefing/trigger", response_model=EmailBriefingResponse)
async def trigger_on_demand_briefing(
    request: BriefingTriggerRequest,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EmailBriefingResponse:
    """
    Trigger a briefing email for any molecule regardless of its briefing_mode.
    This bypasses the preference check — it's manual/on-demand.
    """
    from app.services.intelligence_service import IntelligenceService

    molecule_result = await db.execute(select(Molecule).where(Molecule.id == request.molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    # Map segments to department (use first segment)
    department = request.segments[0] if request.segments else "market_access"

    payload = EmailBriefingRequest(
        molecule_id=request.molecule_id,
        department=department,
        format="html",
        since_days=request.since_days,
        bypass_preferences=True,
        recipients=[request.recipient],
    )

    service = IntelligenceService()
    response = await service.generate_email_briefing(payload, db)

    # Override recipient for JSON response consistency
    response.recipient = request.recipient

    # Update last_briefing_sent_at
    molecule.last_briefing_sent_at = datetime.now(UTC)  # type: ignore[assignment]
    await db.commit()

    return response


@router.get("/alert-check")
async def check_alert_threshold(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """
    For molecules in 'alert_only' mode, check if top threat score >= threshold.
    Returns: {"should_alert": true/false, "top_score": int, "threshold": int}
    """
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    if molecule.briefing_mode != "alert_only" or not molecule.is_monitored:
        return {
            "should_alert": False,
            "top_score": 0,
            "threshold": molecule.alert_threshold,
            "reason": "Molecule is not in alert_only mode or is not monitored",
        }

    # Run the same query as /intelligence/top-threats with limit=1
    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.competitor))
        .where(Event.molecule_id == molecule_id)
        .where(Event.verification_status == "verified")
        .order_by(Event.threat_score.desc())
        .limit(1)
    )
    top_event = events_result.scalar_one_or_none()

    if top_event is None or top_event.threat_score is None:
        return {
            "should_alert": False,
            "top_score": 0,
            "threshold": molecule.alert_threshold,
            "reason": "No verified events with threat scores found",
        }

    should_alert = top_event.threat_score >= molecule.alert_threshold

    return {
        "should_alert": should_alert,
        "top_score": top_event.threat_score,
        "threshold": molecule.alert_threshold,
        "event": EventRead.model_validate(top_event) if should_alert else None,
    }
