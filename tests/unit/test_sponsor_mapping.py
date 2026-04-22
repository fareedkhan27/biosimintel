from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.services.ingestion.sponsor_mapping import SponsorMappingService


@dataclass
class MockCompetitor:
    id: str
    canonical_name: str
    tier: int
    asset_code: str | None
    parent_company: str | None


@pytest.fixture
def mock_competitors() -> list[MockCompetitor]:
    return [
        MockCompetitor(
            id=str(uuid4()),
            canonical_name="Amgen",
            tier=1,
            asset_code="ABP 206",
            parent_company=None,
        ),
        MockCompetitor(
            id=str(uuid4()),
            canonical_name="Sandoz",
            tier=2,
            asset_code="JPB898",
            parent_company="Novartis AG",
        ),
        MockCompetitor(
            id=str(uuid4()),
            canonical_name="Henlius",
            tier=3,
            asset_code="HLX18",
            parent_company=None,
        ),
        MockCompetitor(
            id=str(uuid4()),
            canonical_name="Intas",
            tier=2,
            asset_code=None,
            parent_company=None,
        ),
    ]


@pytest.fixture
def service(mock_competitors: list[MockCompetitor]) -> SponsorMappingService:
    return SponsorMappingService(mock_competitors)  # type: ignore[arg-type]


# Override the autouse database fixture from conftest.py so these pure unit
# tests do not require a running Postgres instance.
@pytest.fixture(autouse=True)
def setup_database() -> None:
    return None


def test_exact_canonical_match(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Amgen", "INDUSTRY")
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Amgen"
    assert result.match_method == "canonical_exact"
    assert result.confidence == 1.0
    assert result.blocked is False
    assert result.flag_for_review is False


def test_exact_alias_match(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Novartis AG", "INDUSTRY")
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Sandoz"
    assert result.match_method == "alias_exact"
    assert result.confidence == 1.0
    assert result.blocked is False
    assert result.flag_for_review is False


def test_exact_alias_case_insensitive(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("novartis ag", "INDUSTRY")
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Sandoz"
    assert result.match_method == "alias_exact"
    assert result.confidence == 1.0
    assert result.blocked is False
    assert result.flag_for_review is False


def test_fuzzy_match_above_threshold(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Amgen Inc.", "INDUSTRY")
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Amgen"
    assert result.match_method == "canonical_fuzzy"
    assert result.confidence >= 0.85
    assert result.blocked is False
    assert result.flag_for_review is False


def test_fuzzy_match_below_threshold(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Acmegen", "INDUSTRY")
    assert result.competitor is None
    assert result.match_method is None
    assert result.confidence == 0.0
    assert result.blocked is False
    assert result.flag_for_review is True


def test_blocked_sponsor_class_nih(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Some Institute", "NIH")
    assert result.competitor is None
    assert result.blocked is True
    assert result.blocked_reason is not None
    assert "NIH" in result.blocked_reason
    assert result.flag_for_review is False


def test_blocked_sponsor_class_network(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Some Network Group", "NETWORK")
    assert result.competitor is None
    assert result.blocked is True
    assert result.blocked_reason is not None
    assert "NETWORK" in result.blocked_reason
    assert result.flag_for_review is False


def test_blocked_pattern_mayo_clinic(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Mayo Clinic", "OTHER")
    assert result.competitor is None
    assert result.blocked is True
    assert result.blocked_reason is not None
    assert "blocked_pattern" in result.blocked_reason
    assert result.flag_for_review is False


def test_blocked_pattern_university(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("University of Texas", "OTHER")
    assert result.competitor is None
    assert result.blocked is True
    assert result.blocked_reason is not None
    assert "blocked_pattern" in result.blocked_reason
    assert result.flag_for_review is False


def test_other_class_allowed_if_matches(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Amgen", "OTHER")
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Amgen"
    assert result.blocked is False
    assert result.flag_for_review is False


def test_asset_code_from_title_fallback(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor(
        "Unknown Sponsor", "INDUSTRY", trial_title="Study of ABP 206 in NSCLC"
    )
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Amgen"
    assert result.match_method == "asset_code"
    assert result.confidence == 0.9
    assert result.blocked is False
    assert result.flag_for_review is False


def test_industry_no_match_flags_review(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("Pfizer Inc", "INDUSTRY")
    assert result.competitor is None
    assert result.match_method is None
    assert result.blocked is False
    assert result.flag_for_review is True


def test_blocked_pattern_substring_match(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor("National Cancer Institute", "OTHER")
    assert result.competitor is None
    assert result.blocked is True
    assert result.blocked_reason is not None
    assert "blocked_pattern" in result.blocked_reason
    assert result.flag_for_review is False


def test_fuzzy_parent_company_match(service: SponsorMappingService) -> None:
    result = service.map_sponsor_to_competitor(
        "Novartis Pharmaceuticals Corporation", "INDUSTRY"
    )
    assert result.competitor is not None
    assert result.competitor.canonical_name == "Sandoz"
    assert result.match_method == "parent_fuzzy"
    assert result.confidence >= 0.85
    assert result.blocked is False
    assert result.flag_for_review is False
