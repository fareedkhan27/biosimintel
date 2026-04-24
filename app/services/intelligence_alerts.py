from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.intelligence_baseline import IntelligenceBaseline
from app.models.molecule import Molecule
from app.schemas.intelligence_alerts import AlertEvent, AlertReport
from app.services.indication_heatmap import build_indication_landscape
from app.services.predictive_timeline import build_launch_timeline, format_stage


async def detect_threshold_breaches(
    molecule_id: UUID,
    db: AsyncSession,
) -> AlertReport:
    """Detect competitive intelligence threshold breaches against last baseline."""
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Molecule")

    # Build current landscape and timeline
    landscape = await build_indication_landscape(molecule_id, db)
    timeline = await build_launch_timeline(molecule_id, db)

    # Load baselines
    baseline_result = await db.execute(
        select(IntelligenceBaseline).where(IntelligenceBaseline.molecule_id == molecule_id)
    )
    baselines = list(baseline_result.scalars().all())
    baseline_map: dict[str, int] = {b.baseline_type: b.baseline_value for b in baselines}  # type: ignore[misc]

    alerts: list[AlertEvent] = []
    now = datetime.now(UTC)

    # 1. VULNERABILITY_SPIKE
    current_vi = landscape.vulnerability_index
    last_vi = baseline_map.get("vulnerability_index", current_vi)
    if current_vi - last_vi >= 20:
        alerts.append(
            AlertEvent(
                alert_type="VULNERABILITY_SPIKE",
                severity="high",
                title="Vulnerability Index Spike",
                description=f"Vulnerability index rose from {last_vi} to {current_vi}.",
                competitor_name=None,
                indication=None,
                old_value=str(last_vi),
                new_value=str(current_vi),
                detected_at=now,
            )
        )

    # 2. NEW_CONTESTED_ZONE
    last_contested = baseline_map.get("contested_zones_count", len(landscape.contested_indications))
    if len(landscape.contested_indications) > last_contested:
        alerts.append(
            AlertEvent(
                alert_type="NEW_CONTESTED_ZONE",
                severity="medium",
                title="New Contested Zone",
                description=f"Contested zones increased to {len(landscape.contested_indications)}.",
                competitor_name=None,
                indication=landscape.contested_indications[-1] if landscape.contested_indications else None,
                old_value=str(last_contested),
                new_value=str(len(landscape.contested_indications)),
                detected_at=now,
            )
        )

    # 3. STAGE_ADVANCEMENT & NEW_COMPETITOR_ENTRY
    # Fetch recent events (last 14 days) to detect changes
    since = now - timedelta(days=14)
    event_result = await db.execute(
        select(Event)
        .where(Event.molecule_id == molecule_id)
        .where(Event.created_at >= since)
    )
    recent_events = list(event_result.scalars().all())

    # Re-fetch competitors properly
    comp_result = await db.execute(
        select(Competitor).where(Competitor.molecule_id == molecule_id)
    )
    competitors = list(comp_result.scalars().all())

    # Check for new competitors (not in baseline)
    baseline_comp_count = baseline_map.get("competitor_count", len(competitors))
    if len(competitors) > baseline_comp_count:
        alerts.append(
            AlertEvent(
                alert_type="NEW_COMPETITOR_ENTRY",
                severity="high",
                title="New Competitor Detected",
                description=f"Competitor count increased from {baseline_comp_count} to {len(competitors)}.",
                competitor_name=None,
                indication=None,
                old_value=str(baseline_comp_count),
                new_value=str(len(competitors)),
                detected_at=now,
            )
        )

    # Stage advancements from recent events
    for evt in recent_events:
        if evt.development_stage and evt.event_type in ("clinical_trial", "regulatory_filing"):
            comp_name = evt.competitor.canonical_name if evt.competitor else "Unknown"
            alerts.append(
                AlertEvent(
                    alert_type="STAGE_ADVANCEMENT",
                    severity="medium",
                    title="Stage Advancement",
                    description=f"{comp_name} advanced to {format_stage(str(evt.development_stage) if evt.development_stage else None)} in {evt.indication or 'unspecified indication'}.",
                    competitor_name=comp_name,
                    indication=evt.indication,  # type: ignore[arg-type]
                    old_value=None,
                    new_value=evt.development_stage,  # type: ignore[arg-type]
                    detected_at=now,
                )
            )

    # 4. LAUNCH_IMMINENT
    for threat in timeline.imminent_threats:
        if threat.months_to_launch <= 6 and threat.confidence_level == "high":
            alerts.append(
                AlertEvent(
                    alert_type="LAUNCH_IMMINENT",
                    severity="critical",
                    title="Imminent Launch Detected",
                    description=f"{threat.competitor_name} estimated launch in {threat.indication} within {threat.months_to_launch} months.",
                    competitor_name=threat.competitor_name,
                    indication=threat.indication,
                    old_value=None,
                    new_value=threat.estimated_launch_quarter,
                    detected_at=now,
                )
            )

    # 5. PATENT_CLIFF_APPROACHING
    from app.services.regulatory_risk import calculate_regulatory_risk_weights
    risk_profile = await calculate_regulatory_risk_weights(molecule_id, db)
    for pc in risk_profile.patent_cliffs:
        if pc.days_to_expiry <= 365 and pc.competitors_active:
            alerts.append(
                AlertEvent(
                    alert_type="PATENT_CLIFF_APPROACHING",
                    severity="high",
                    title="Patent Cliff Approaching",
                    description=f"Patent {pc.patent_number or 'N/A'} for {pc.indication} expires in {pc.days_to_expiry} days with active competitors.",
                    competitor_name=None,
                    indication=pc.indication,
                    old_value=None,
                    new_value=str(pc.expiry_date),
                    detected_at=now,
                )
            )

    critical_count = sum(1 for a in alerts if a.severity == "critical")
    high_count = sum(1 for a in alerts if a.severity == "high")

    return AlertReport(
        molecule_id=molecule_id,
        molecule_name=molecule.molecule_name or "Unknown",  # type: ignore[arg-type]
        alerts=alerts,
        critical_count=critical_count,
        high_count=high_count,
        has_critical=critical_count > 0,
        generated_at=now,
    )


async def record_intelligence_baseline(
    molecule_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Record current intelligence state as baseline for future comparison."""
    landscape = await build_indication_landscape(molecule_id, db)

    comp_result = await db.execute(
        select(Competitor).where(Competitor.molecule_id == molecule_id)
    )
    competitor_count = len(list(comp_result.scalars().all()))

    baselines = [
        IntelligenceBaseline(
            molecule_id=molecule_id,
            baseline_type="vulnerability_index",
            baseline_value=landscape.vulnerability_index,
        ),
        IntelligenceBaseline(
            molecule_id=molecule_id,
            baseline_type="contested_zones_count",
            baseline_value=len(landscape.contested_indications),
        ),
        IntelligenceBaseline(
            molecule_id=molecule_id,
            baseline_type="competitor_count",
            baseline_value=competitor_count,
        ),
        IntelligenceBaseline(
            molecule_id=molecule_id,
            baseline_type="white_spaces_count",
            baseline_value=len(landscape.white_space_indications),
        ),
    ]

    for b in baselines:
        db.add(b)
    await db.commit()

    return {
        "molecule_id": str(molecule_id),
        "recorded_at": datetime.now(UTC).isoformat(),
        "baselines": {b.baseline_type: b.baseline_value for b in baselines},
    }
