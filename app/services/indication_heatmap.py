"""Competitive Indication Landscape analytics engine.

Builds a heatmap matrix of competitor activity across indications,
with multi-factor heat scoring and strategic metrics.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule
from app.schemas.indication_heatmap import (
    CompetitorColumn,
    HeatmapCell,
    IndicationLandscape,
)

# ---------------------------------------------------------------------------
# Stage normalization & weights
# ---------------------------------------------------------------------------

_STAGE_WEIGHTS: dict[str, int] = {
    "preclinical": 5,
    "pre_clinical": 5,
    "phase1": 15,
    "phase_1": 15,
    "phase_1_2": 20,
    "phase2": 30,
    "phase_2": 30,
    "phase_2_3": 40,
    "phase3": 50,
    "phase_3": 50,
    "phase_3b": 55,
    "bla": 75,
    "filed_bla": 75,
    "filed": 70,
    "under_review": 80,
    "approved": 100,
    "launched": 100,
    "suspended": 0,
    "discontinued": 0,
}

_STAGE_ABBREVIATIONS: dict[str, str] = {
    "preclinical": "PC",
    "pre_clinical": "PC",
    "phase1": "P1",
    "phase_1": "P1",
    "phase_1_2": "P1/2",
    "phase2": "P2",
    "phase_2": "P2",
    "phase_2_3": "P2/3",
    "phase3": "P3",
    "phase_3": "P3",
    "phase_3b": "P3b",
    "bla": "BLA",
    "filed_bla": "BLA",
    "filed": "BLA",
    "under_review": "REV",
    "approved": "AP",
    "launched": "AP",
    "suspended": "SUS",
    "discontinued": "DIS",
}


def _normalize_stage(stage: str | None) -> str:
    if not stage:
        return "preclinical"
    key = stage.lower().strip().replace(" ", "_")
    return key if key in _STAGE_WEIGHTS else "preclinical"


def _stage_weight(stage: str | None) -> int:
    return _STAGE_WEIGHTS.get(_normalize_stage(stage), 5)


def _stage_abbreviation(stage: str | None) -> str:
    return _STAGE_ABBREVIATIONS.get(_normalize_stage(stage), "PC")


# ---------------------------------------------------------------------------
# Heat score algorithm
# ---------------------------------------------------------------------------

def _compute_heat_score(
    avg_threat: float,
    event_count: int,
    latest_stage: str | None,
) -> int:
    """Multi-factor heat score (0-100)."""
    stage_w = _stage_weight(latest_stage)
    score = (avg_threat * 0.6) + (min(event_count * 8, 40)) + (stage_w * 0.2)
    return min(100, round(score))


# ---------------------------------------------------------------------------
# Core landscape builder
# ---------------------------------------------------------------------------

async def build_indication_landscape(
    molecule_id: UUID,
    db: AsyncSession,
    min_threat_threshold: int = 0,
) -> IndicationLandscape:
    """Build the full competitive indication landscape for a molecule.

    Args:
        molecule_id: Target molecule UUID.
        db: Async SQLAlchemy session.
        min_threat_threshold: Minimum threat score to include an event
            in cell averages (default 0 includes all).

    Returns:
        IndicationLandscape with matrix, strategic metrics, and metadata.
    """
    # --- Fetch molecule ---
    molecule_result = await db.execute(
        select(Molecule).where(Molecule.id == molecule_id)
    )
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Molecule")

    # --- Fetch all relevant events (uses composite index) ---
    stmt = (
        select(Event)
        .where(Event.molecule_id == molecule_id)
        .where(Event.indication.isnot(None))
        .where(Event.competitor_id.isnot(None))
    )
    if min_threat_threshold > 0:
        stmt = stmt.where(Event.threat_score >= min_threat_threshold)

    events_result = await db.execute(stmt)
    events: list[Event] = list(events_result.scalars().all())

    # --- Aggregate by (indication, competitor) ---
    cell_agg = dict[str, Any]
    agg: dict[tuple[str, UUID], cell_agg] = defaultdict(
        lambda: {
            "events": [],
            "threat_scores": [],
            "max_stage_weight": -1,
            "latest_created": None,
        }
    )

    for evt in events:
        indication: str = (evt.indication or "").strip()
        if not indication:
            continue
        competitor_id: UUID | None = evt.competitor_id  # type: ignore[assignment]
        if competitor_id is None:
            continue

        key = (indication, competitor_id)
        bucket = agg[key]
        bucket["events"].append(evt)

        if evt.threat_score is not None:
            bucket["threat_scores"].append(evt.threat_score)

        # Track latest stage by weight
        sw = _stage_weight(evt.development_stage)  # type: ignore[arg-type]
        if sw > bucket["max_stage_weight"]:
            bucket["max_stage_weight"] = sw
            bucket["latest_stage"] = evt.development_stage

        # Track latest created_at
        created = evt.created_at
        if created and (
            bucket["latest_created"] is None or created > bucket["latest_created"]
        ):
            bucket["latest_created"] = created

    # --- Fetch competitor metadata ---
    competitor_ids = {cid for _, cid in agg}
    competitors_map: dict[UUID, Competitor] = {}
    if competitor_ids:
        comp_result = await db.execute(
            select(Competitor).where(Competitor.id.in_(competitor_ids))
        )
        for comp in comp_result.scalars().all():
            competitors_map[comp.id] = comp  # type: ignore[index]

    # --- Build matrix dimensions ---
    all_indications = sorted({ind for ind, _ in agg})
    all_competitors = sorted(
        competitors_map.values(),
        key=lambda c: c.canonical_name or "",
    )
    competitor_index = {c.id: idx for idx, c in enumerate(all_competitors)}  # type: ignore[misc]

    # --- Build cells ---
    cells_by_pos: dict[tuple[int, int], HeatmapCell] = {}
    for (indication, cid), bucket in agg.items():
        if indication not in all_indications:
            continue
        row_idx = all_indications.index(indication)
        col_idx = competitor_index.get(cid)
        if col_idx is None:
            continue

        threat_scores: list[int] = bucket["threat_scores"]
        avg_threat = round(sum(threat_scores) / len(threat_scores), 1) if threat_scores else 0.0
        max_threat = max(threat_scores) if threat_scores else 0
        event_count = len(bucket["events"])
        latest_stage: str = bucket.get("latest_stage") or "preclinical"
        latest_created: datetime | None = bucket["latest_created"]

        heat_score = _compute_heat_score(avg_threat, event_count, latest_stage)

        cell = HeatmapCell(
            competitor_id=cid,
            indication=indication,
            event_count=event_count,
            avg_threat_score=avg_threat,
            max_threat_score=max_threat,
            latest_stage=latest_stage,
            latest_event_date=latest_created or datetime.now(UTC),
            heat_score=heat_score,
            stage_abbreviation=_stage_abbreviation(latest_stage),
        )
        cells_by_pos[(row_idx, col_idx)] = cell

    # Assemble matrix rows
    matrix: list[list[HeatmapCell | None]] = []
    for r in range(len(all_indications)):
        row: list[HeatmapCell | None] = []
        for c in range(len(all_competitors)):
            row.append(cells_by_pos.get((r, c)))
        matrix.append(row)

    # --- Strategic metrics ---
    # White space: indications with zero competitor activity
    indications_with_activity = {ind for ind, _ in agg}
    white_space_indications = [
        ind for ind in all_indications if ind not in indications_with_activity
    ]
    # Since all_indications is built from agg keys, this will be empty unless
    # we also consider the molecule's configured indications. Let's use
    # molecule.indications if available.
    configured_indications: list[str] = []
    if molecule.indications and isinstance(molecule.indications, dict):
        configured_indications = list(molecule.indications.keys())
    elif molecule.indications and isinstance(molecule.indications, list):
        configured_indications = [str(i) for i in molecule.indications]

    if configured_indications:
        white_space_indications = sorted(
            {
                ind
                for ind in configured_indications
                if ind not in indications_with_activity
            }
        )

    # Contested: indications with 3+ competitors
    competitor_count_by_indication: dict[str, int] = defaultdict(int)
    for ind, _cid in agg:
        competitor_count_by_indication[ind] += 1
    contested_indications = sorted(
        [
            ind
            for ind, count in competitor_count_by_indication.items()
            if count >= 3
        ]
    )

    # Competitor focus scores
    competitor_columns: list[CompetitorColumn] = []
    focus_data: dict[UUID, dict[str, Any]] = defaultdict(
        lambda: {"indications": set(), "max_heat": 0}
    )
    for (ind, cid), bucket in agg.items():
        focus_data[cid]["indications"].add(ind)
        # compute heat for this cell
        threat_scores = bucket["threat_scores"]
        avg_threat = round(sum(threat_scores) / len(threat_scores), 1) if threat_scores else 0.0
        event_count = len(bucket["events"])
        latest_stage = bucket.get("latest_stage") or "preclinical"
        heat = _compute_heat_score(avg_threat, event_count, latest_stage)
        if heat > focus_data[cid]["max_heat"]:
            focus_data[cid]["max_heat"] = heat

    for comp in all_competitors:
        data = focus_data[comp.id]
        breadth = len(data["indications"])
        depth = data["max_heat"]
        if breadth > 3:
            focus_type = "broad"
        elif breadth > 1:
            focus_type = "focused"
        else:
            focus_type = "single"
        competitor_columns.append(
            CompetitorColumn(
                id=comp.id,
                name=comp.canonical_name or "Unknown",
                cik=comp.cik,
                breadth_score=breadth,
                depth_score=depth,
                focus_type=focus_type,
            )
        )

    # Vulnerability index: weighted average of heat scores across contested indications
    if contested_indications:
        contested_heats: list[int] = []
        for ind in contested_indications:
            for (i, _c), bucket in agg.items():
                if i != ind:
                    continue
                threat_scores = bucket["threat_scores"]
                avg_threat = (
                    round(sum(threat_scores) / len(threat_scores), 1)
                    if threat_scores
                    else 0.0
                )
                event_count = len(bucket["events"])
                latest_stage = bucket.get("latest_stage") or "preclinical"
                heat = _compute_heat_score(avg_threat, event_count, latest_stage)
                contested_heats.append(heat)
        vulnerability_index = (
            round(sum(contested_heats) / len(contested_heats)) if contested_heats else 0
        )
    else:
        vulnerability_index = 0

    return IndicationLandscape(
        molecule_id=molecule_id,
        molecule_name=molecule.molecule_name or "Unknown",
        indications=all_indications,
        competitors=competitor_columns,
        matrix=matrix,
        white_space_indications=white_space_indications,
        contested_indications=contested_indications,
        vulnerability_index=vulnerability_index,
        generated_at=datetime.now(UTC),
        total_events_analyzed=len(events),
    )
