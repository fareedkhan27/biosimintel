from __future__ import annotations

from app.models.event import Event

THREAT_LEVELS: list[tuple[int, str, str]] = [
    (80, "Critical", "#DC2626"),
    (60, "High", "#EA580C"),
    (40, "Moderate", "#D97706"),
    (20, "Low", "#16A34A"),
    (0, "Minimal", "#9CA3AF"),
]

THREAT_GUIDE_TEXT = (
    "🔴 80-100 Critical | 🟠 60-79 High | 🟡 40-59 Moderate | "
    "🟢 20-39 Low | ⚪ 0-19 Minimal"
)


_STAGE_DESCRIPTORS: dict[str, str] = {
    "pre_clinical": "Pre-clinical study",
    "phase_1": "Phase 1 trial",
    "phase_1_2": "Phase 1/2 trial",
    "phase_2": "Phase 2 trial",
    "phase_3": "Phase 3 trial",
    "phase_3b": "Phase 3b trial",
    "filed_bla": "BLA filing",
    "under_review": "Application under review",
    "approved": "Approved therapy",
    "launched": "Marketed product",
    "suspended": "Suspended trial",
    "discontinued": "Discontinued program",
}


def _impact_phrase(score: int, stage: str | None, event_type: str | None) -> str:
    high_threat_stages = {"filed_bla", "under_review", "approved", "launched"}
    market_entry_stages = {"phase_3", "phase_3b", "filed_bla", "under_review"}

    if score >= 80:
        if event_type == "regulatory_filing" or stage in high_threat_stages:
            return "imminent launch threat"
        return "severe near-term competitive risk"
    if score >= 60:
        if stage in market_entry_stages:
            return "approaching market entry"
        return "significant competitive pressure"
    if score >= 40:
        if stage in market_entry_stages:
            return "approaching market entry"
        if stage == "phase_2":
            return "mid-stage development"
        return "moderate competitive activity"
    if score >= 20:
        return "limited near-term impact"
    return "minimal near-term impact"


def interpret_threat_score(event: Event) -> tuple[str, str, str]:
    """Return (threat_label, threat_color, threat_explanation) for an event.

    The interpretation is purely presentational and does NOT modify the
    underlying scoring algorithm.
    """
    score: int = event.threat_score or 0  # type: ignore[assignment]

    label = "Minimal"
    color = "#9CA3AF"
    for min_score, lvl_label, lvl_color in THREAT_LEVELS:
        if score >= min_score:
            label = lvl_label
            color = lvl_color
            break

    development_stage: str | None = event.development_stage  # type: ignore[assignment]
    country: str | None = event.country  # type: ignore[assignment]
    event_type: str | None = event.event_type  # type: ignore[assignment]

    stage_desc = _STAGE_DESCRIPTORS.get(
        development_stage or "", "Competitive event"
    ) if development_stage else "Competitive event"

    market = country or "global market"
    impact = _impact_phrase(score, development_stage, event_type)

    explanation = f"{label} — {stage_desc} in {market}, {impact}"

    return label, color, explanation
