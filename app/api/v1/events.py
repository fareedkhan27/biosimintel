from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.event import Event
from app.schemas.event import EventRead

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("", response_model=list[EventRead])
async def list_events(
    molecule_id: UUID | None = Query(None),
    competitor_id: UUID | None = Query(None),
    event_type: str | None = Query(None),
    traffic_light: str | None = Query(None),
    indication: str | None = Query(None),
    country: str | None = Query(None),
    _date_from: str | None = Query(None),
    _date_to: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Event]:
    """List events with filters."""
    stmt = select(Event)
    if molecule_id:
        stmt = stmt.where(Event.molecule_id == molecule_id)
    if competitor_id:
        stmt = stmt.where(Event.competitor_id == competitor_id)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if traffic_light:
        stmt = stmt.where(Event.traffic_light == traffic_light)
    if indication:
        stmt = stmt.where(Event.indication == indication)
    if country:
        stmt = stmt.where(Event.country == country)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Event:
    """Get event with competitor, source, and provenance."""
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise NotFoundException("Event")
    return event


@router.get("/{event_id}/provenance", response_model=list[dict[str, Any]])
async def get_event_provenance(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get full provenance trail for an event."""
    from app.models.data_provenance import DataProvenance
    result = await db.execute(
        select(DataProvenance).where(DataProvenance.event_id == event_id)
    )
    provenance = list(result.scalars().all())
    return [
        {
            "field_name": p.field_name,
            "raw_value": p.raw_value,
            "normalized_value": p.normalized_value,
            "extraction_method": p.extraction_method,
            "confidence": float(p.confidence),
            "verified_by": p.verified_by,
        }
        for p in provenance
    ]


@router.post("/{event_id}/interpret", response_model=EventRead, status_code=status.HTTP_200_OK)
async def interpret_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Event:
    """Trigger AI interpretation for an event (idempotent)."""
    from app.services.ai.interpretation import InterpretationService
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise NotFoundException("Event")

    service = InterpretationService()
    await service.interpret(event, db)
    await db.commit()
    await db.refresh(event)
    return event


async def get_provenance_data(db: AsyncSession, event_id: UUID) -> dict[str, Any] | None:
    """Fetch enriched provenance data for HTML rendering."""
    from app.models.data_provenance import DataProvenance
    from app.models.source_document import SourceDocument

    result = await db.execute(
        select(Event, SourceDocument)
        .outerjoin(SourceDocument, Event.source_document_id == SourceDocument.id)
        .where(Event.id == event_id)
    )
    row = result.first()
    if not row:
        return None

    event, source_doc = row

    sponsor_result = await db.execute(
        select(DataProvenance)
        .where(DataProvenance.event_id == event_id)
        .where(DataProvenance.field_name == "sponsor")
    )
    sponsor_prov = sponsor_result.scalar_one_or_none()
    sponsor = None
    if sponsor_prov:
        sponsor = sponsor_prov.normalized_value or sponsor_prov.raw_value

    return {
        "nct_id": source_doc.external_id if source_doc else None,
        "title": source_doc.title if source_doc else None,
        "sponsor": sponsor,
        "phase": event.event_subtype,
        "status": event.verification_status,
        "first_posted": (
            source_doc.published_at.isoformat()
            if source_doc and source_doc.published_at
            else (event.created_at.isoformat() if event.created_at else None)
        ),
        "last_updated": event.updated_at.isoformat() if event.updated_at else None,
        "threat_score": event.threat_score or 0,
        "summary": event.summary,
        "ingested_at": (
            source_doc.fetched_at.isoformat()
            if source_doc and source_doc.fetched_at
            else (event.created_at.isoformat() if event.created_at else None)
        ),
    }


@router.get("/{event_id}/provenance/view", response_class=HTMLResponse)
async def get_provenance_view(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """
    Human-readable HTML view of provenance data.
    The existing JSON endpoint at /{event_id}/provenance remains untouched.
    """
    data = await get_provenance_data(db, event_id)
    if not data:
        raise HTTPException(status_code=404, detail="Event not found")

    return templates.TemplateResponse(
        request,
        "provenance.html",
        {
            "nct_id": data.get("nct_id"),
            "title": data.get("title"),
            "sponsor": data.get("sponsor"),
            "phase": data.get("phase"),
            "status": data.get("status"),
            "first_posted": data.get("first_posted"),
            "last_updated": data.get("last_updated"),
            "threat_score": data.get("threat_score", 0),
            "summary": data.get("summary"),
            "ingested_at": data.get("ingested_at"),
        },
    )
