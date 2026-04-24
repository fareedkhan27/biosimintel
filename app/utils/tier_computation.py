from __future__ import annotations

from typing import Any

TIER_CONFIG: dict[int, dict[str, str]] = {
    1: {"label": "Tier 1", "color": "#DC2626", "badge_class": "tier-badge-1"},
    2: {"label": "Tier 2", "color": "#EA580C", "badge_class": "tier-badge-2"},
    3: {"label": "Tier 3", "color": "#CA8A04", "badge_class": "tier-badge-3"},
    4: {"label": "Tier 4", "color": "#6B7280", "badge_class": "tier-badge-4"},
}


def _markets_overlap(primary_markets: list[str] | None, targets: list[str]) -> bool:
    """Check if any market in primary_markets matches a target (case-insensitive)."""
    if not primary_markets:
        return False
    markets_normalized = {m.lower() for m in primary_markets}
    targets_normalized = {t.lower() for t in targets}
    return bool(markets_normalized & targets_normalized)


def compute_competitor_tier(competitor: Any) -> dict[str, Any]:
    """Compute dynamic tier for a competitor based on real-time data.

    Returns a dict with tier metadata and a one-line explanation.
    The competitor object is duck-typed — any object with the required
    attributes works (ORM model, MagicMock, dataclass, etc.).
    """
    stage = (competitor.development_stage or "").lower()
    status = (competitor.status or "active").lower()
    markets = competitor.primary_markets or []
    partnership = (competitor.partnership_status or "").lower()

    # Special rule: inactive status → Tier 4 regardless of stage
    if status != "active":
        tier_number = 4
        reason = f"Status is '{competitor.status}' — dropped to Tier 4"
        config = TIER_CONFIG[tier_number]
        return {
            "tier_number": tier_number,
            "tier_label": config["label"],
            "tier_color": config["color"],
            "tier_badge_class": config["badge_class"],
            "reason": reason,
        }

    # Special rule: launched → always Tier 1 regardless of markets
    if stage == "launched":
        tier_number = 1
        reason = "Product launched — always Tier 1"
        config = TIER_CONFIG[tier_number]
        return {
            "tier_number": tier_number,
            "tier_label": config["label"],
            "tier_color": config["color"],
            "tier_badge_class": config["badge_class"],
            "reason": reason,
        }

    # Tier 1: phase_3 + US/EU markets
    if stage == "phase_3" and _markets_overlap(markets, ["US", "EU"]):
        tier_number = 1
        reason = "Phase 3 with US/EU market ambition"
        config = TIER_CONFIG[tier_number]
        return {
            "tier_number": tier_number,
            "tier_label": config["label"],
            "tier_color": config["color"],
            "tier_badge_class": config["badge_class"],
            "reason": reason,
        }

    # Tier 2: phase_1_2 / phase_2 / phase_3 + (US/EU OR partnership)
    if stage in {"phase_1_2", "phase_2", "phase_3"} and (
        _markets_overlap(markets, ["US", "EU"]) or partnership == "partnership"
    ):
        tier_number = 2
        if partnership == "partnership":
            reason = f"{stage.replace('_', ' ').title()} stage with strategic partnership"
        else:
            reason = f"{stage.replace('_', ' ').title()} stage with US/EU market ambition"
        config = TIER_CONFIG[tier_number]
        return {
            "tier_number": tier_number,
            "tier_label": config["label"],
            "tier_color": config["color"],
            "tier_badge_class": config["badge_class"],
            "reason": reason,
        }

    # Tier 3: phase_1 OR (pre_clinical + Global/US/EU markets)
    if stage == "phase_1" or (
        stage == "pre_clinical" and _markets_overlap(markets, ["Global", "US", "EU"])
    ):
        tier_number = 3
        if stage == "phase_1":
            reason = "Phase 1 trial underway"
        else:
            reason = "Pre-clinical with global market ambition"
        config = TIER_CONFIG[tier_number]
        return {
            "tier_number": tier_number,
            "tier_label": config["label"],
            "tier_color": config["color"],
            "tier_badge_class": config["badge_class"],
            "reason": reason,
        }

    # Tier 4: everything else
    tier_number = 4
    if stage == "pre_clinical":
        reason = "Pre-clinical with local markets only"
    elif stage == "suspended":
        reason = "Development suspended"
    else:
        reason = f"{stage.replace('_', ' ').title() or 'Unknown'} stage with limited market scope"
    config = TIER_CONFIG[tier_number]
    return {
        "tier_number": tier_number,
        "tier_label": config["label"],
        "tier_color": config["color"],
        "tier_badge_class": config["badge_class"],
        "reason": reason,
    }
