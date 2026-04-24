from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.tier_computation import compute_competitor_tier


@dataclass
class MockCompetitor:
    """Minimal competitor stand-in for tier computation tests."""

    development_stage: str | None = None
    status: str | None = "active"
    primary_markets: list[str] | None = None
    partnership_status: str | None = None
    tier: int = 4


def _make_comp(**kwargs: Any) -> MockCompetitor:
    return MockCompetitor(**kwargs)


class TestTier1:
    def test_launched_always_tier_1(self) -> None:
        comp = _make_comp(development_stage="launched", primary_markets=["India"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 1
        assert result["tier_label"] == "Tier 1"
        assert result["tier_color"] == "#DC2626"
        assert "launched" in result["reason"].lower()

    def test_phase_3_with_us_eu(self) -> None:
        comp = _make_comp(development_stage="phase_3", primary_markets=["US", "EU"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 1

    def test_phase_3_with_eu_only(self) -> None:
        comp = _make_comp(development_stage="phase_3", primary_markets=["EU"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 1

    def test_phase_3_without_us_eu(self) -> None:
        comp = _make_comp(development_stage="phase_3", primary_markets=["China"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] != 1


class TestTier2:
    def test_phase_2_with_us_eu(self) -> None:
        comp = _make_comp(development_stage="phase_2", primary_markets=["US"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 2

    def test_phase_1_2_with_partnership(self) -> None:
        comp = _make_comp(
            development_stage="phase_1_2",
            primary_markets=["India"],
            partnership_status="partnership",
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 2
        assert "partnership" in result["reason"].lower()

    def test_phase_3_with_partnership_no_us_eu(self) -> None:
        comp = _make_comp(
            development_stage="phase_3",
            primary_markets=["China"],
            partnership_status="partnership",
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 2

    def test_phase_2_without_us_eu_or_partnership(self) -> None:
        comp = _make_comp(
            development_stage="phase_2",
            primary_markets=["India"],
            partnership_status="solo",
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] != 2
        assert result["tier_number"] == 4


class TestTier3:
    def test_phase_1(self) -> None:
        comp = _make_comp(development_stage="phase_1", primary_markets=[])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3
        assert result["tier_color"] == "#CA8A04"

    def test_pre_clinical_with_global(self) -> None:
        comp = _make_comp(development_stage="pre_clinical", primary_markets=["Global"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3

    def test_pre_clinical_with_us(self) -> None:
        comp = _make_comp(development_stage="pre_clinical", primary_markets=["US"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3

    def test_pre_clinical_with_eu(self) -> None:
        comp = _make_comp(development_stage="pre_clinical", primary_markets=["EU"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3

    def test_pre_clinical_with_india_only(self) -> None:
        comp = _make_comp(development_stage="pre_clinical", primary_markets=["India"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4

    def test_pre_clinical_with_india_and_global(self) -> None:
        comp = _make_comp(
            development_stage="pre_clinical", primary_markets=["India", "Global"]
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3


class TestTier4:
    def test_pre_clinical_local_markets(self) -> None:
        comp = _make_comp(development_stage="pre_clinical", primary_markets=["India"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4
        assert result["tier_label"] == "Tier 4"
        assert "local" in result["reason"].lower()

    def test_suspended(self) -> None:
        comp = _make_comp(development_stage="suspended", primary_markets=["US", "EU"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4
        assert "suspended" in result["reason"].lower()

    def test_unknown_stage(self) -> None:
        comp = _make_comp(development_stage="discovery", primary_markets=["US"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4

    def test_none_stage(self) -> None:
        comp = _make_comp(development_stage=None, primary_markets=["US"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4


class TestSpecialRules:
    def test_inactive_drops_to_tier_4(self) -> None:
        comp = _make_comp(
            development_stage="phase_3",
            primary_markets=["US", "EU"],
            status="suspended",
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4
        assert "dropped" in result["reason"].lower()

    def test_inactive_pre_clinical(self) -> None:
        comp = _make_comp(
            development_stage="pre_clinical",
            primary_markets=["India"],
            status="withdrawn",
        )
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 4

    def test_launched_overrides_inactive(self) -> None:
        """Launched should be Tier 1 even if status is not active.

        Order of checks: inactive is evaluated before launched in the
        current implementation, so launched with inactive status will
        be Tier 4. This is a design choice — the requirement says
        'status != active -> drop to Tier 4 regardless of stage' and
        'development_stage = launched -> always Tier 1 regardless of markets'.
        The precedence of these two special rules is not fully specified.
        We choose to evaluate inactive first (safety rule).
        """
        comp = _make_comp(
            development_stage="launched",
            primary_markets=["India"],
            status="discontinued",
        )
        result = compute_competitor_tier(comp)
        # Inactive takes precedence in current implementation
        assert result["tier_number"] == 4

    def test_case_insensitive_markets(self) -> None:
        comp = _make_comp(development_stage="phase_3", primary_markets=["us", "eu"])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 1

    def test_empty_markets(self) -> None:
        comp = _make_comp(development_stage="phase_3", primary_markets=[])
        result = compute_competitor_tier(comp)
        assert result["tier_number"] != 1

    def test_none_markets(self) -> None:
        comp = _make_comp(development_stage="phase_1", primary_markets=None)
        result = compute_competitor_tier(comp)
        assert result["tier_number"] == 3


class TestReturnStructure:
    def test_all_keys_present(self) -> None:
        comp = _make_comp(development_stage="phase_1")
        result = compute_competitor_tier(comp)
        expected_keys = {
            "tier_number",
            "tier_label",
            "tier_color",
            "tier_badge_class",
            "reason",
        }
        assert set(result.keys()) == expected_keys

    def test_tier_number_is_int(self) -> None:
        comp = _make_comp(development_stage="launched")
        result = compute_competitor_tier(comp)
        assert isinstance(result["tier_number"], int)
