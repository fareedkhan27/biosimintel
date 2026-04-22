from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.engine.verification import (
    RejectedEvent,
    VerificationEngine,
    VerifiedEvent,
)


@pytest.fixture
def mock_event() -> MagicMock:
    event = MagicMock()
    event.event_type = "clinical_trial"
    return event


@pytest.fixture
def mock_provenance() -> list[MagicMock]:
    p = MagicMock()
    p.extraction_method = "clinicaltrials_gov"
    p.confidence = 0.96
    return [p]


def test_verify_clinical_trial_pass(mock_event: MagicMock, mock_provenance: list[MagicMock]) -> None:
    engine = VerificationEngine()
    result = engine.verify(mock_event, mock_provenance)
    assert isinstance(result, VerifiedEvent)
    assert result.confidence >= 0.95


def test_verify_clinical_trial_fail_source(mock_event: MagicMock) -> None:
    engine = VerificationEngine()
    p = MagicMock()
    p.extraction_method = "press_release"
    p.confidence = 0.96
    result = engine.verify(mock_event, [p])
    assert isinstance(result, RejectedEvent)


def test_verify_clinical_trial_fail_confidence(mock_event: MagicMock) -> None:
    engine = VerificationEngine()
    p = MagicMock()
    p.extraction_method = "clinicaltrials_gov"
    p.confidence = 0.90
    result = engine.verify(mock_event, [p])
    assert isinstance(result, RejectedEvent)


def test_fuzzy_match_competitor() -> None:
    engine = VerificationEngine()
    result = engine.fuzzy_match_competitor("Amgen", ["Amgen", "pfizer", "novartis"])
    assert result == "Amgen"


def test_fuzzy_match_no_match() -> None:
    engine = VerificationEngine()
    result = engine.fuzzy_match_competitor("xyz", ["amgen", "pfizer"])
    assert result is None
