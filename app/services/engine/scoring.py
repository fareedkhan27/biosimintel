from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.event import Event

STAGE_POINTS: dict[str, int] = {
    "pre_clinical": 13,
    "phase_1": 25,
    "phase_1_2": 38,
    "phase_2": 63,
    "phase_3": 100,
    "phase_3b": 113,
    "filed_bla": 125,
    "under_review": 138,
    "approved": 150,
    "launched": 163,
    "suspended": 50,
    "discontinued": 0,
}

TIER_POINTS: dict[int, int] = {
    1: 63,
    2: 50,
    3: 38,
    4: 25,
}

LOE_MULTIPLIERS: dict[str, float] = {
    "India": 2.0,
    "United States": 1.5,
    "EU": 1.1,
    "Japan": 0.6,
    "China": 0.9,
    "Global": 1.0,
}

INDICATION_POINTS: dict[str, int] = {
    "HIGH": 50,
    "MEDIUM": 38,
    "LOW": 25,
}

CONFIDENCE_POINTS: dict[str, int] = {
    "verified": 25,
    "single_source": 18,
    "unverified": 13,
}

RECENCY_POINTS: dict[str, int] = {
    "lt_30": 13,
    "lt_90": 8,
    "lt_1y": 3,
    "old": 0,
}

BASE_WEIGHTS: dict[str, float] = {
    "development_stage": 0.30,
    "competitor_tier": 0.20,
    "geography_loe": 0.20,
    "indication_priority": 0.15,
    "data_confidence": 0.10,
    "event_recency": 0.05,
}


def _recency_bucket(event_date: datetime | None) -> str:
    if event_date is None:
        return "old"
    now = datetime.now(UTC)
    delta = now - event_date
    if delta < timedelta(days=30):
        return "lt_30"
    if delta < timedelta(days=90):
        return "lt_90"
    if delta < timedelta(days=365):
        return "lt_1y"
    return "old"


class ScoringEngine:
    """Deterministic scoring engine — pure function, same inputs always produce same output."""

    def score(self, event: Event) -> dict[str, Any]:
        stage = (event.development_stage or "").lower().replace(" ", "_").replace("-", "_")
        stage_pts = STAGE_POINTS.get(stage, 0)

        tier = event.competitor.tier if event.competitor else 4
        tier_pts = TIER_POINTS.get(tier, 10)

        country: str = event.country or "Global"  # type: ignore[assignment]
        loe_mult = LOE_MULTIPLIERS.get(country, 1.0)
        geo_pts = 50 * loe_mult

        ind_priority = (event.indication_priority or "LOW").upper()
        ind_pts = INDICATION_POINTS.get(ind_priority, 10)

        verification = (event.verification_status or "unverified").lower()
        if verification == "verified" and event.verified_sources_count and event.verified_sources_count > 1:
            conf_pts = CONFIDENCE_POINTS["verified"]
        elif verification == "verified":
            conf_pts = CONFIDENCE_POINTS["single_source"]
        else:
            conf_pts = CONFIDENCE_POINTS["unverified"]

        recency = _recency_bucket(event.event_date)  # type: ignore[arg-type]
        rec_pts = RECENCY_POINTS.get(recency, 0)

        breakdown = {
            "development_stage": round(stage_pts * BASE_WEIGHTS["development_stage"], 2),
            "competitor_tier": round(tier_pts * BASE_WEIGHTS["competitor_tier"], 2),
            "geography_loe": round(geo_pts * BASE_WEIGHTS["geography_loe"], 2),
            "indication_priority": round(ind_pts * BASE_WEIGHTS["indication_priority"], 2),
            "data_confidence": round(conf_pts * BASE_WEIGHTS["data_confidence"], 2),
            "event_recency": round(rec_pts * BASE_WEIGHTS["event_recency"], 2),
        }

        total = sum(breakdown.values())
        threat_score = max(0, min(100, round(total)))

        if threat_score <= 44:
            traffic_light = "Green"
        elif threat_score <= 74:
            traffic_light = "Amber"
        else:
            traffic_light = "Red"

        return {
            "threat_score": threat_score,
            "traffic_light": traffic_light,
            "breakdown": breakdown,
            "inputs": {
                "stage": stage,
                "tier": tier,
                "country": country,
                "indication_priority": ind_priority,
                "verification": verification,
                "recency": recency,
            },
        }
