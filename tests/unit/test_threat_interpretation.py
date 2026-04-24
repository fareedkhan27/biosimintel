from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.utils.threat_interpretation import THREAT_GUIDE_TEXT, interpret_threat_score


@pytest.fixture
def mock_event() -> MagicMock:
    event = MagicMock()
    event.threat_score = 42
    event.development_stage = "phase_3"
    event.country = "United States"
    event.event_type = "clinical_trial"
    return event


def test_interpret_threat_score_moderate(mock_event: MagicMock) -> None:
    label, color, explanation = interpret_threat_score(mock_event)
    assert label == "Moderate"
    assert color == "#D97706"
    assert "Phase 3 trial" in explanation
    assert "United States" in explanation
    assert "approaching market entry" in explanation


def test_interpret_threat_score_critical(mock_event: MagicMock) -> None:
    mock_event.threat_score = 88
    mock_event.development_stage = "filed_bla"
    mock_event.country = "EU"
    label, color, explanation = interpret_threat_score(mock_event)
    assert label == "Critical"
    assert color == "#DC2626"
    assert "BLA filing" in explanation
    assert "imminent launch threat" in explanation


def test_interpret_threat_score_high(mock_event: MagicMock) -> None:
    mock_event.threat_score = 65
    mock_event.development_stage = "phase_2"
    mock_event.country = "Germany"
    label, color, explanation = interpret_threat_score(mock_event)
    assert label == "High"
    assert color == "#EA580C"
    assert "Phase 2 trial" in explanation
    assert "significant competitive pressure" in explanation


def test_interpret_threat_score_low(mock_event: MagicMock) -> None:
    mock_event.threat_score = 29
    mock_event.development_stage = "pre_clinical"
    mock_event.country = "India"
    label, color, explanation = interpret_threat_score(mock_event)
    assert label == "Low"
    assert color == "#16A34A"
    assert "Pre-clinical study" in explanation
    assert "limited near-term impact" in explanation


def test_interpret_threat_score_minimal(mock_event: MagicMock) -> None:
    mock_event.threat_score = 5
    mock_event.development_stage = None
    mock_event.country = None
    mock_event.event_type = "press_release"
    label, color, explanation = interpret_threat_score(mock_event)
    assert label == "Minimal"
    assert color == "#9CA3AF"
    assert "Competitive event" in explanation
    assert "global market" in explanation


def test_threat_guide_text() -> None:
    assert "Critical" in THREAT_GUIDE_TEXT
    assert "High" in THREAT_GUIDE_TEXT
    assert "Moderate" in THREAT_GUIDE_TEXT
    assert "Low" in THREAT_GUIDE_TEXT
    assert "Minimal" in THREAT_GUIDE_TEXT
