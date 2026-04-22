from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.engine.scoring import ScoringEngine


@pytest.fixture
def mock_event() -> MagicMock:
    event = MagicMock()
    event.development_stage = "phase_3"
    event.competitor = MagicMock()
    event.competitor.tier = 1
    event.country = "United States"
    event.indication_priority = "HIGH"
    event.verification_status = "verified"
    event.verified_sources_count = 2
    event.event_date = datetime.now(UTC) - timedelta(days=10)
    return event


def test_scoring_engine_basic(mock_event: MagicMock) -> None:
    engine = ScoringEngine()
    result = engine.score(mock_event)
    assert 0 <= result["threat_score"] <= 100
    assert result["traffic_light"] in ("Green", "Amber", "Red")
    assert "breakdown" in result
    assert "inputs" in result


def test_scoring_engine_red_light(mock_event: MagicMock) -> None:
    mock_event.development_stage = "launched"
    mock_event.country = "India"
    mock_event.indication_priority = "HIGH"
    engine = ScoringEngine()
    result = engine.score(mock_event)
    assert result["traffic_light"] == "Red"
    assert result["threat_score"] >= 75


def test_scoring_engine_green_light(mock_event: MagicMock) -> None:
    mock_event.development_stage = "pre_clinical"
    mock_event.competitor.tier = 4
    mock_event.country = "Japan"
    mock_event.indication_priority = "LOW"
    mock_event.verification_status = "unverified"
    mock_event.event_date = datetime.now(UTC) - timedelta(days=400)
    engine = ScoringEngine()
    result = engine.score(mock_event)
    assert result["traffic_light"] == "Green"
    assert result["threat_score"] <= 44
