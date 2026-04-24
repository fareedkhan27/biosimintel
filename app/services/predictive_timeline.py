from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule
from app.schemas.predictive_timeline import LaunchEstimate, LaunchTimeline

STAGE_DISPLAY_MAP: dict[str, str] = {
    "pre_clinical": "Pre-Clinical",
    "preclinical": "Pre-Clinical",
    "phase1": "Phase 1",
    "phase_1": "Phase 1",
    "phase2": "Phase 2",
    "phase_2": "Phase 2",
    "phase3": "Phase 3",
    "phase_3": "Phase 3",
    "phase_3b": "Phase 3",
    "phase1_2": "Phase 1/2",
    "phase_1_2": "Phase 1/2",
    "phase2_3": "Phase 2/3",
    "phase_2_3": "Phase 2/3",
    "bla": "BLA Filed",
    "filed_bla": "BLA Filed",
    "filed": "BLA Filed",
    "under_review": "Under Review",
    "approved": "Approved",
    "launched": "Launched",
    "suspended": "Suspended",
}

PHASE_BASE_MONTHS: dict[str, dict[str, Any]] = {
    "pre_clinical": {"next": "phase1", "months": 18},
    "phase1": {"next": "phase2", "months": 12},
    "phase_1": {"next": "phase2", "months": 12},
    "phase2": {"next": "phase3", "months": 18},
    "phase_2": {"next": "phase3", "months": 18},
    "phase_2_3": {"next": "phase3", "months": 18},
    "phase3": {"next": "bla", "months": 24},
    "phase_3": {"next": "bla", "months": 24},
    "phase_3b": {"next": "bla", "months": 24},
    "bla": {"next": "approved", "months": 12},
    "filed_bla": {"next": "approved", "months": 12},
    "filed": {"next": "approved", "months": 12},
    "under_review": {"next": "approved", "months": 6},
    "approved": {"next": None, "months": 0},
    "launched": {"next": None, "months": 0},
}


def format_stage(stage: str | None) -> str:
    """Return a human-readable stage label."""
    if not stage:
        return "Unknown"
    key = stage.lower().strip().replace(" ", "_").replace("-", "_")
    return STAGE_DISPLAY_MAP.get(key, stage.replace("_", " ").title())

VELOCITY_MULTIPLIERS: dict[str, float] = {
    "accelerated": 0.85,
    "standard": 1.0,
    "slow": 1.15,
    "stalled": 1.4,
}


def _normalize_stage(stage: str | None) -> str:
    if not stage:
        return "pre_clinical"
    key = stage.lower().strip().replace(" ", "_").replace("-", "_")
    return key if key in PHASE_BASE_MONTHS else "pre_clinical"


def _events_to_velocity(events_count: int) -> str:
    if events_count >= 3:
        return "accelerated"
    if events_count == 2:
        return "standard"
    if events_count == 1:
        return "slow"
    return "stalled"


def _compute_confidence(current_stage: str, velocity: str) -> str:
    stage = _normalize_stage(current_stage)
    if stage in ("phase3", "phase_3", "phase_3b", "bla", "filed_bla", "filed", "under_review"):
        return "high" if velocity in ("accelerated", "standard") else "medium"
    if stage in ("phase2", "phase_2", "phase_2_3"):
        return "medium" if velocity in ("standard", "slow") else "low"
    if stage == "approved":
        return "high"
    return "low"


def _quarter_from_date(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


async def build_launch_timeline(
    molecule_id: UUID,
    db: AsyncSession,
) -> LaunchTimeline:
    """Build a predictive launch timeline for all competitors of a molecule."""
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Molecule")

    # Fetch all competitors
    competitors_result = await db.execute(
        select(Competitor).where(Competitor.molecule_id == molecule_id)
    )
    competitors = list(competitors_result.scalars().all())

    # Fetch all events for these competitors — filter out unspecified indications
    competitor_ids = [c.id for c in competitors]
    events: list[Event] = []
    if competitor_ids:
        events_result = await db.execute(
            select(Event)
            .where(Event.molecule_id == molecule_id)
            .where(Event.competitor_id.in_(competitor_ids))
            .where(Event.indication.isnot(None))
            .where(Event.indication != "")
            .where(Event.indication != "Unspecified")
        )
        events = list(events_result.scalars().all())

    # Group events by competitor
    events_by_competitor: dict[UUID, list[Event]] = defaultdict(list)
    for evt in events:
        cid = evt.competitor_id
        if cid is not None:
            events_by_competitor[cid].append(evt)  # type: ignore[index]

    # Group events by competitor+indication
    events_by_comp_ind: dict[tuple[UUID, str], list[Event]] = defaultdict(list)
    for evt in events:
        cid = evt.competitor_id
        ind = (evt.indication or "").strip()
        if cid is not None and ind:
            events_by_comp_ind[(cid, ind)].append(evt)  # type: ignore[index]

    estimates: list[LaunchEstimate] = []
    now = datetime.now(UTC)
    cutoff_90d = now - timedelta(days=90)

    for comp in competitors:
        comp_events = events_by_competitor.get(comp.id, [])  # type: ignore[call-overload]
        # Get explicitly named indications for this competitor
        indications = sorted({
            (e.indication or "").strip()
            for e in comp_events
            if e.indication and e.indication.strip() and e.indication.strip() != "Unspecified"
        })
        if not indications:
            # Skip competitors with no explicit indications in the timeline table
            # They remain in the tier table and heat map via other services
            continue

        for indication in indications:
            ind_events = events_by_comp_ind.get((comp.id, indication), [])  # type: ignore[arg-type]
            if not ind_events:
                ind_events = comp_events  # fallback to all competitor events

            # Latest stage and event date
            latest_event = max(
                ind_events,
                key=lambda e: e.event_date or e.created_at or datetime.min.replace(tzinfo=UTC),
                default=None,
            )
            latest_stage = comp.development_stage or "pre_clinical"
            if latest_event and latest_event.development_stage:
                latest_stage = latest_event.development_stage

            latest_date = latest_event.event_date or latest_event.created_at if latest_event else now

            # Events in last 90 days
            events_90d = [e for e in ind_events if (e.created_at or e.event_date or datetime.min.replace(tzinfo=UTC)) >= cutoff_90d]
            velocity_label = _events_to_velocity(len(events_90d))
            velocity_multiplier = VELOCITY_MULTIPLIERS[velocity_label]

            # Walk phase chain
            current = _normalize_stage(latest_stage)  # type: ignore[arg-type]
            total_months = 0.0
            visited: set[str] = set()
            while current and current not in visited:
                visited.add(current)
                cfg = PHASE_BASE_MONTHS.get(current)
                if not cfg or cfg["next"] is None:
                    break
                total_months += cfg["months"] * velocity_multiplier
                current = cfg["next"]

            estimated_launch = latest_date + timedelta(days=int(total_months * 30.44))
            estimated_launch_date = estimated_launch.date()
            months_to_launch = max(0, int(total_months))

            estimates.append(
                LaunchEstimate(
                    competitor_id=comp.id,  # type: ignore[arg-type]
                    competitor_name=comp.canonical_name or "Unknown",  # type: ignore[arg-type]
                    indication=indication,
                    current_stage=format_stage(latest_stage),  # type: ignore[arg-type]
                    estimated_launch_date=estimated_launch_date,
                    estimated_launch_quarter=_quarter_from_date(estimated_launch_date),
                    months_to_launch=months_to_launch,
                    confidence_level=_compute_confidence(latest_stage, velocity_label),  # type: ignore[arg-type]
                    velocity_multiplier=velocity_multiplier,
                    events_last_90_days=len(events_90d),
                )
            )

    # Group by quarter
    timeline_by_quarter: dict[str, list[LaunchEstimate]] = defaultdict(list)
    for est in estimates:
        timeline_by_quarter[est.estimated_launch_quarter].append(est)

    # Imminent threats: <= 12 months and not approved/launched
    imminent = [
        e for e in estimates
        if e.months_to_launch <= 12 and e.confidence_level in ("high", "medium") and e.current_stage.lower() not in ("approved", "launched")
    ]

    # Pipeline summary by confidence
    pipeline_summary: dict[str, int] = defaultdict(int)
    for e in estimates:
        pipeline_summary[e.confidence_level] += 1

    return LaunchTimeline(
        molecule_id=molecule_id,
        molecule_name=molecule.molecule_name or "Unknown",  # type: ignore[arg-type]
        estimates=estimates,
        timeline_by_quarter=dict(timeline_by_quarter),
        imminent_threats=imminent,
        pipeline_summary=dict(pipeline_summary),
        generated_at=now,
    )
