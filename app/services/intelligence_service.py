from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule
from app.models.sec_filing import SecFiling
from app.schemas.indication_heatmap import IndicationLandscape
from app.schemas.intelligence import (
    BriefingRequest,
    BriefingResponse,
    BriefingSection,
    EmailBriefingRequest,
    EmailBriefingResponse,
)
from app.services.indication_heatmap import build_indication_landscape
from app.services.intelligence_alerts import detect_threshold_breaches
from app.services.llm_insights import generate_executive_narrative
from app.services.predictive_timeline import build_launch_timeline, format_stage
from app.services.regulatory_risk import calculate_regulatory_risk_weights
from app.utils.threat_interpretation import THREAT_GUIDE_TEXT, interpret_threat_score
from app.utils.tier_computation import compute_competitor_tier

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
_email_template_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
_template_dir = Path(__file__).resolve().parent.parent / "templates"
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(str(_email_template_dir)),
                FileSystemLoader(str(_template_dir)),
            ]),
            autoescape=select_autoescape(["html", "xml"]),
        )
        _jinja_env.filters["format_stage"] = format_stage
    return _jinja_env


def _vulnerability_styles(index: int) -> tuple[str, str, str]:
    """Return (color, background_color, label) for vulnerability index."""
    if index < 40:
        return "#065f46", "#ecfdf5", "Low Risk"
    if index < 60:
        return "#92400e", "#fef3c7", "Moderate Risk"
    if index < 80:
        return "#9a3412", "#fff7ed", "Elevated Risk"
    return "#991b1b", "#fef2f2", "High Risk"


def _generate_heatmap_insights(landscape: IndicationLandscape) -> list[str]:
    """Auto-generate strategic narrative bullets from landscape data."""
    insights: list[str] = []

    competitors = landscape.competitors
    if competitors:
        most_active = max(competitors, key=lambda c: c.breadth_score)
        insights.append(
            f"{most_active.name} is the most active competitor across "
            f"{most_active.breadth_score} indication(s) (focus: {most_active.focus_type})."
        )

    max_heat = 0
    top_indication = ""
    for row in landscape.matrix:
        for cell in row:
            if cell and cell.heat_score > max_heat:
                max_heat = cell.heat_score
                top_indication = cell.indication
    if top_indication:
        insights.append(
            f"The highest threat concentration is in {top_indication} "
            f"with a heat score of {max_heat}."
        )

    if landscape.white_space_indications:
        first_ws = landscape.white_space_indications[0]
        insights.append(
            f"Consider prioritizing market access strategy for {first_ws} "
            "where no biosimilar activity has been detected."
        )

    return insights


def _render_heatmap_email_fragment(
    landscape: IndicationLandscape,
    patent_cliffs: list[dict[str, Any]] | None = None,
) -> str:
    """Render the heatmap macro into an email-safe HTML fragment."""
    if not landscape.indications:
        return (
            '<div style="text-align:center;padding:32px;border:2px dashed #cbd5e1;'
            'border-radius:8px;font-family:system-ui,sans-serif;color:#64748b;">'
            "No Indication-Level Intelligence Available. Competitive activity is being monitored. "
            "This section will populate as clinical trial and regulatory data is ingested."
            "</div>"
        )

    env = _get_jinja_env()
    vi_color, vi_bg, _vi_label = _vulnerability_styles(landscape.vulnerability_index)
    insights = _generate_heatmap_insights(landscape)

    executive_summary = (
        f"{landscape.molecule_name} faces concentrated competition in "
        f"{len(landscape.contested_indications)} indication(s), with "
        f"{len(landscape.white_space_indications)} white-space opportunity(ies) remaining. "
        f"Overall vulnerability index: {landscape.vulnerability_index}/100."
    )

    # Build patent lookup by indication for ⏳ icons
    patent_lookup: dict[str, dict[str, Any]] = {}
    for pc in (patent_cliffs or []):
        ind = pc.get("indication", "") if isinstance(pc, dict) else pc.indication
        if ind:
            patent_lookup[ind] = pc if isinstance(pc, dict) else pc.model_dump()

    fragment_template = env.get_template("heatmap_email_fragment.html")
    return fragment_template.render(
        landscape=landscape,
        executive_summary=executive_summary,
        vi_bg=vi_bg,
        vi_fg=vi_color,
        insights=insights,
        patent_lookup=patent_lookup,
    )


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


def _format_indication_display(event: Event) -> str:
    """Return a human-readable indication or fallback for event cards."""
    event_type: str = event.event_type  # type: ignore[assignment]
    if event_type == "clinical_trial":
        indication: str | None = event.indication  # type: ignore[assignment]
        return indication or ""
    if event_type == "press_release":
        return "Press Release"
    if event_type == "regulatory_filing":
        country: str | None = event.country  # type: ignore[assignment]
        return country or "Regulatory Filing"
    if event_type in ("sec_filing", "financial_disclosure"):
        return "Financial Disclosure"
    return ""


def _format_event_meta_line(event: Event) -> str:
    """Build the meta line (asset, stage, indication, country) for an event card."""
    parts: list[str] = []
    asset_code = event.competitor.asset_code if event.competitor else "N/A"
    if asset_code and asset_code != "N/A":
        parts.append(str(asset_code))
    development_stage: str | None = event.development_stage  # type: ignore[assignment]
    if development_stage:
        parts.append(development_stage.replace("_", " ").title())
    indication_display = _format_indication_display(event)
    if indication_display:
        parts.append(indication_display)
    country: str | None = event.country  # type: ignore[assignment]
    parts.append(country or "Global")
    return " • ".join(parts)


_STAGE_DISPLAY_MAP: dict[str, str] = {
    "phase_1_2": "Phase 1/2",
    "phase_3": "Phase 3",
    "phase_1": "Phase 1",
    "phase_2": "Phase 2",
    "pre_clinical": "Pre-Clinical",
    "launched": "Launched",
    "suspended": "Suspended",
    "filed": "Filed",
    "approved": "Approved",
}


def _format_stage_display(stage: str | None) -> str:
    """Human-readable development stage."""
    if not stage:
        return "Unknown"
    return _STAGE_DISPLAY_MAP.get(stage.lower(), stage.replace("_", " ").title())


def _format_latest_signal(event: Event | None, competitor: Any) -> str:
    """Format the most recent event as a specific, actionable signal string.

    For launched competitors, returns a live-market message.
    For competitors with no recent events, returns 'Monitoring'.
    """
    comp_stage = (competitor.development_stage or "").lower()
    if comp_stage == "launched":
        markets = competitor.primary_markets or []
        launch = competitor.launch_window or "Recently"
        if markets:
            return f"Live in {', '.join(markets)} — {launch}"
        return f"Live — {launch}"

    if event is None:
        return "Monitoring"

    event_type: str = event.event_type  # type: ignore[assignment]
    event_date: datetime | None = event.event_date  # type: ignore[assignment]
    date_str = event_date.strftime("%b %d") if event_date else "recently"

    if event_type == "clinical_trial":
        nct_id: str | None = None
        if event.source_document and getattr(event.source_document, "external_id", None):
            nct_id = event.source_document.external_id
        dev_stage: str | None = event.development_stage  # type: ignore[assignment]
        stage_str = _STAGE_DISPLAY_MAP.get((dev_stage or "").lower(), "Trial")
        if nct_id and nct_id.upper().startswith("NCT"):
            return f"Trial {nct_id} posted {date_str}"
        return f"{stage_str} posted {date_str}"

    if event_type == "regulatory_filing":
        country: str | None = event.country  # type: ignore[assignment]
        market = country or "global market"
        return f"Regulatory filing in {market} ({date_str})"

    if event_type in ("sec_filing", "financial_disclosure"):
        return f"SEC disclosure filed {date_str}"

    if event_type == "press_release":
        return f"Press release posted {date_str}"

    label = event_type.replace("_", " ").title()
    return f"{label} ({date_str})"





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
            .options(selectinload(Event.source_document))
            .where(Event.molecule_id == payload.molecule_id)
            .where(Event.verification_status == "verified")
            .where(Event.competitor_id.isnot(None))
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

    async def _build_financial_intelligence(
        self,
        molecule_id: UUID,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Query recent SEC filings for competitors with a CIK."""
        cutoff = datetime.utcnow() - timedelta(days=90)

        competitors_result = await db.execute(
            select(Competitor)
            .where(Competitor.molecule_id == molecule_id)
            .where(Competitor.cik.isnot(None))
        )
        competitors = list(competitors_result.scalars().all())
        if not competitors:
            return []

        competitor_ids = [c.id for c in competitors]
        filings_result = await db.execute(
            select(SecFiling)
            .where(SecFiling.competitor_id.in_(competitor_ids))
            .where(SecFiling.filing_date >= cutoff)
            .where(SecFiling.form_type.in_(["10-K", "8-K", "10-Q", "6-K"]))
            .order_by(SecFiling.filing_date.desc())
        )
        all_filings = list(filings_result.scalars().all())

        filings_by_competitor: dict[Any, list[SecFiling]] = {}
        for filing in all_filings:
            filings_by_competitor.setdefault(filing.competitor_id, []).append(filing)

        financial_intelligence: list[dict[str, Any]] = []
        description_map = {
            "8-K": "Current Report",
            "10-K": "Annual Report",
            "10-Q": "Quarterly Report",
            "6-K": "Foreign Filing",
        }
        for comp in competitors:
            comp_filings = filings_by_competitor.get(comp.id, [])[:3]
            if not comp_filings:
                continue
            financial_intelligence.append({
                "competitor_name": comp.canonical_name,
                "competitor_tier": comp.tier,
                "filings": [
                    {
                        "form_type": f.form_type,
                        "filing_date": f.filing_date.strftime("%b %d, %Y"),
                        "description": description_map.get(str(f.form_type), str(f.form_type)),
                        "primary_doc_url": f.primary_doc_url,
                        "accession_number": f.accession_number,
                    }
                    for f in comp_filings
                ],
            })

        return financial_intelligence

    async def _build_competitive_landscape(
        self,
        molecule_id: UUID,
        db: AsyncSession,
        recent_events: list[Event],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Build competitive landscape table and detect tier movements.

        Returns:
            (landscape_rows, tier_movements)
        """
        competitors_result = await db.execute(
            select(Competitor).where(Competitor.molecule_id == molecule_id)
        )
        competitors = list(competitors_result.scalars().all())

        if not competitors:
            return [], []

        # Map competitor_id -> latest recent event for signal display
        latest_event_by_competitor: dict[Any, Event] = {}
        for evt in recent_events:
            cid = evt.competitor_id
            existing = latest_event_by_competitor.get(cid)
            if existing is None:
                latest_event_by_competitor[cid] = evt
            else:
                # Prefer event_date, fallback to created_at
                evt_date = evt.event_date or evt.created_at
                existing_date = existing.event_date or existing.created_at
                if evt_date and existing_date and evt_date > existing_date:
                    latest_event_by_competitor[cid] = evt

        landscape_rows: list[dict[str, Any]] = []
        tier_movements: list[dict[str, Any]] = []

        for comp in competitors:
            computed = compute_competitor_tier(comp)

            if computed["tier_number"] != comp.tier:
                tier_movements.append({
                    "competitor_name": comp.canonical_name,
                    "from_tier": comp.tier,
                    "to_tier": computed["tier_number"],
                    "reason": computed["reason"],
                })
                # Update cached tier for next week's baseline
                comp.tier = computed["tier_number"]
                db.add(comp)

            latest_evt = latest_event_by_competitor.get(comp.id)
            latest_signal = _format_latest_signal(latest_evt, comp)

            landscape_rows.append({
                "competitor_name": comp.canonical_name,
                "asset_code": comp.asset_code,
                "development_stage": _format_stage_display(comp.development_stage),  # type: ignore[arg-type]
                "primary_markets": comp.primary_markets or [],
                "launch_window": comp.launch_window or "—",
                "latest_signal": latest_signal,
                "tier_number": computed["tier_number"],
                "tier_label": computed["tier_label"],
                "tier_color": computed["tier_color"],
                "tier_badge_class": computed["tier_badge_class"],
                "created_at": comp.created_at,
            })

        # Group by tier (1 first, 4 last), then sort by created_at DESC within tier
        landscape_rows.sort(
            key=lambda r: (
                r["tier_number"],
                -(r["created_at"].timestamp() if r["created_at"] else 0),
            )
        )

        return landscape_rows, tier_movements

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
            .options(selectinload(Event.source_document))
            .where(Event.molecule_id == payload.molecule_id)
            .where(Event.verification_status == "verified")
            .where(Event.competitor_id.isnot(None))
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
            threat_label, threat_color, threat_explanation = interpret_threat_score(e)
            meta_line = _format_event_meta_line(e)
            event_cards.append({
                "competitor_name": competitor,
                "asset_code": asset_code,
                "development_stage": format_stage(str(e.development_stage) if e.development_stage else None),
                "indication": e.indication,
                "indication_display": _format_indication_display(e),
                "meta_line": meta_line,
                "country": e.country,
                "threat_score": e.threat_score,
                "threat_label": threat_label,
                "threat_color": threat_color,
                "threat_explanation": threat_explanation,
                "traffic_light": e.traffic_light,
                "summary": e.summary,
                "why_it_matters": e.ai_why_it_matters,
                "recommended_action": e.ai_recommended_action,
                "provenance_url": f"{settings.API_BASE_URL}/api/v1/events/{e.id}/provenance/view",
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

        financial_intelligence = await self._build_financial_intelligence(
            payload.molecule_id, db
        )

        competitive_landscape, tier_movements = await self._build_competitive_landscape(
            payload.molecule_id, db, events
        )

        # Persist any tier updates so next week's baseline is current
        await db.commit()

        # Build indication landscape for strategic heatmap section
        indication_landscape = await build_indication_landscape(
            payload.molecule_id, db
        )

        # Phase 3C: AI Strategic Advisor data
        llm_narrative = await generate_executive_narrative(payload.molecule_id, db)
        timeline = await build_launch_timeline(payload.molecule_id, db)
        alert_report = await detect_threshold_breaches(payload.molecule_id, db)
        risk_profile = await calculate_regulatory_risk_weights(payload.molecule_id, db)

        # Filter alerts for email (critical/high only)
        email_alerts = [
            a for a in alert_report.alerts
            if a.severity in ("critical", "high")
        ]

        # Build patent lookup for heatmap icons
        patent_cliffs_data: list[dict[str, Any]] = [p.model_dump() for p in risk_profile.patent_cliffs]
        heatmap_html = _render_heatmap_email_fragment(indication_landscape, patent_cliffs=patent_cliffs_data)
        heatmap_insights = _generate_heatmap_insights(indication_landscape)

        # Planning horizon filter: only show launches within next 7 years for email
        horizon_years = 7
        cutoff_date = datetime.now(UTC).date() + timedelta(days=horizon_years * 365)
        visible_estimates = [e for e in timeline.estimates if e.estimated_launch_date <= cutoff_date]
        hidden_count = len(timeline.estimates) - len(visible_estimates)
        horizon_note = ""
        if hidden_count > 0:
            horizon_note = (
                f"{hidden_count} additional pipeline entries extend beyond {horizon_years} years. "
                f"View full timeline at {settings.API_BASE_URL}/api/v1/intelligence/timeline/view?molecule_id={payload.molecule_id}"
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
                financial_intelligence=financial_intelligence,
                threat_guide=THREAT_GUIDE_TEXT,
                competitive_landscape=competitive_landscape,
                tier_movements=tier_movements,
                heatmap_html=heatmap_html,
                heatmap_insights=heatmap_insights,
                indication_landscape=indication_landscape,
                llm_narrative=llm_narrative,
                timeline=timeline,
                visible_estimates=visible_estimates,
                hidden_count=hidden_count,
                horizon_note=horizon_note,
                alerts=email_alerts,
                patent_cliffs=risk_profile.patent_cliffs,
                molecule_id=str(payload.molecule_id),
                insights=llm_narrative.key_insights,
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
                "financial_intelligence": financial_intelligence,
                "threat_guide": THREAT_GUIDE_TEXT,
                "competitive_landscape": competitive_landscape,
                "tier_movements": tier_movements,
                "indication_landscape": indication_landscape.model_dump(mode="json"),
                "heatmap_insights": heatmap_insights,
                "llm_narrative": llm_narrative.model_dump(mode="json"),
                "timeline": timeline.model_dump(mode="json"),
                "alerts": [a.model_dump(mode="json") for a in email_alerts],
                "patent_cliffs": [p.model_dump(mode="json") for p in risk_profile.patent_cliffs],
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
