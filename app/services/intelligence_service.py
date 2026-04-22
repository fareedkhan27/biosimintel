from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.core.logging import get_logger
from app.models.event import Event
from app.models.molecule import Molecule
from app.schemas.intelligence import (
    BriefingRequest,
    BriefingResponse,
    BriefingSection,
    EmailBriefingRequest,
    EmailBriefingResponse,
)

logger = get_logger(__name__)

# Regional routing: country/region keywords -> email distribution
REGIONAL_ROUTING: dict[str, str] = {
    "india": settings.APAC_EMAIL,
    "united states": settings.NA_EMAIL,
    "us": settings.NA_EMAIL,
    "european union": settings.EMEA_EMAIL,
    "eu": settings.EMEA_EMAIL,
    "germany": settings.EMEA_EMAIL,
    "france": settings.EMEA_EMAIL,
    "uk": settings.EMEA_EMAIL,
    "united kingdom": settings.EMEA_EMAIL,
    "spain": settings.EMEA_EMAIL,
    "italy": settings.EMEA_EMAIL,
    "japan": settings.APAC_EMAIL,
    "china": settings.APAC_EMAIL,
    "australia": settings.APAC_EMAIL,
}

# Jinja2 environment for email templates
_template_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
    return _jinja_env


def _resolve_region_email(country: str | None, region: str | None) -> str:
    """Resolve destination email based on event geography."""
    for key in [country, region]:
        if key:
            normalized = key.lower().strip()
            if normalized in REGIONAL_ROUTING:
                return REGIONAL_ROUTING[normalized]
    return settings.EXECUTIVE_EMAIL


def _resolve_competitor_name(event: Event) -> str:
    """Resolve competitor name with fallback chain."""
    if event.competitor and event.competitor.canonical_name:
        return str(event.competitor.canonical_name)
    direct_name = getattr(event, "competitor_name", None)
    if direct_name:
        return str(direct_name)
    return "Unidentified Competitor"


class IntelligenceService:
    """Department briefing generation service — uses ONLY verified data."""

    async def generate_briefing(
        self,
        payload: BriefingRequest,
        db: AsyncSession,
    ) -> BriefingResponse:
        molecule_result = await db.execute(select(Molecule).where(Molecule.id == payload.molecule_id))
        molecule = molecule_result.scalar_one_or_none()
        if molecule is None:
            raise NotFoundException("Molecule")

        since = datetime.now(UTC) - timedelta(days=payload.since_days)

        events_result = await db.execute(
            select(Event)
            .options(selectinload(Event.competitor))
            .where(Event.molecule_id == payload.molecule_id)
            .where(Event.verification_status == "verified")
            .where(Event.created_at >= since)
            .order_by(Event.threat_score.desc())
        )
        events = list(events_result.scalars().all())

        departments = payload.departments or ["market_access"]
        sections: dict[str, BriefingSection] = {}

        for dept in departments:
            sections[dept] = self._build_section(dept, molecule, events)

        return BriefingResponse(
            molecule_id=payload.molecule_id,
            departments=sections,
        )

    async def generate_email_briefing(
        self,
        payload: EmailBriefingRequest,
        db: AsyncSession,
    ) -> EmailBriefingResponse:
        """Generate an email-ready briefing with regional routing."""
        molecule_result = await db.execute(select(Molecule).where(Molecule.id == payload.molecule_id))
        molecule = molecule_result.scalar_one_or_none()
        if molecule is None:
            raise NotFoundException("Molecule")

        since = datetime.now(UTC) - timedelta(days=payload.since_days)

        events_result = await db.execute(
            select(Event)
            .options(selectinload(Event.competitor))
            .where(Event.molecule_id == payload.molecule_id)
            .where(Event.verification_status == "verified")
            .where(Event.created_at >= since)
            .order_by(Event.threat_score.desc())
        )
        events = list(events_result.scalars().all())

        # Determine region from highest-priority event
        region_email = settings.EXECUTIVE_EMAIL
        region_label = "Global"
        if events:
            top_event = events[0]
            region_email = _resolve_region_email(top_event.country, top_event.region)  # type: ignore[arg-type]
            region_label = str(top_event.country or top_event.region or "Global")

        # Build context for template
        event_cards: list[dict[str, Any]] = []
        milestones: list[dict[str, Any]] = []
        for e in events:
            competitor = _resolve_competitor_name(e)
            asset_code = e.competitor.asset_code if e.competitor else "N/A"
            event_cards.append({
                "competitor_name": competitor,
                "asset_code": asset_code,
                "development_stage": e.development_stage,
                "indication": e.indication,
                "country": e.country,
                "threat_score": e.threat_score,
                "traffic_light": e.traffic_light,
                "summary": e.summary,
                "why_it_matters": e.ai_why_it_matters,
                "recommended_action": e.ai_recommended_action,
                "provenance_url": f"{settings.API_BASE_URL}/api/v1/events/{e.id}/provenance",
            })
            if e.event_date:
                milestones.append({
                    "date": e.event_date.strftime("%Y-%m-%d"),
                    "competitor": competitor,
                    "milestone": f"{e.event_type}: {e.summary or 'No summary'}",
                    "traffic_light": e.traffic_light,
                })

        executive_summary = (
            f"{len(events)} verified competitive events for {molecule.molecule_name} "
            f"in the last {payload.since_days} days. "
        )
        if events:
            top = events[0]
            comp = _resolve_competitor_name(top)
            executive_summary += (
                f"Top threat: {comp} ({top.development_stage or 'unknown'}) "
                f"with score {top.threat_score} in {top.country or 'unknown market'}."
            )
        else:
            executive_summary += "No significant competitive activity detected."

        subject = (
            f"[{payload.department.replace('_', ' ').title()}] "
            f"Weekly Briefing: {molecule.molecule_name} — {len(events)} events"
        )

        if payload.format == "html":
            env = _get_jinja_env()
            template = env.get_template("weekly_briefing.html")
            html = template.render(
                subject=subject,
                department=payload.department,
                report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
                executive_summary=executive_summary,
                events=event_cards,
                milestones=milestones,
            )
            return EmailBriefingResponse(
                html=html,
                subject=subject,
                recipient=region_email,
                from_email=settings.DEFAULT_FROM_EMAIL,
                event_count=len(events),
                region=region_label,
            )

        # JSON format
        return EmailBriefingResponse(
            json_payload={
                "executive_summary": executive_summary,
                "events": event_cards,
                "milestones": milestones,
                "department": payload.department,
                "molecule_name": molecule.molecule_name,
            },
            subject=subject,
            recipient=region_email,
            from_email=settings.DEFAULT_FROM_EMAIL,
            event_count=len(events),
            region=region_label,
        )

    def _build_section(
        self,
        dept: str,
        molecule: Molecule,
        events: list[Event],
    ) -> BriefingSection:
        """Build a briefing section from verified events only."""
        executive_summary = (
            f"Briefing for {dept} on {molecule.molecule_name}: "
            f"{len(events)} verified competitive events in the reporting period. "
        )

        if events:
            top_event = events[0]
            competitor = _resolve_competitor_name(top_event)
            executive_summary += (
                f"Highest threat is {competitor} ({top_event.development_stage or 'unknown stage'}) "
                f"with a threat score of {top_event.threat_score}."
            )
        else:
            executive_summary += "No significant competitive activity detected."

        market_sections: list[dict[str, Any]] = []
        for e in events:
            competitor = _resolve_competitor_name(e)
            market_sections.append({
                "competitor": competitor,
                "event_type": e.event_type,
                "development_stage": e.development_stage,
                "indication": e.indication,
                "country": e.country,
                "threat_score": e.threat_score,
                "traffic_light": e.traffic_light,
                "summary": e.summary,
            })

        milestones: list[dict[str, Any]] = []
        for e in events:
            if e.event_date:
                competitor = _resolve_competitor_name(e)
                milestones.append({
                    "date": e.event_date.isoformat(),
                    "competitor": competitor,
                    "milestone": f"{e.event_type}: {e.summary or 'No summary'}",
                    "traffic_light": e.traffic_light,
                })

        return BriefingSection(
            executive_summary=executive_summary,
            market_sections=market_sections,
            milestones=milestones,
        )
