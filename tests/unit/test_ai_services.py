from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.interpretation import InterpretationService
from app.services.ai.qa_engine import QAEngine


@pytest.mark.asyncio
async def test_interpretation_service_already_interpreted() -> None:
    svc = InterpretationService()
    mock_event = MagicMock()
    mock_event.ai_interpreted_at = datetime.now(UTC)
    mock_event.id = "test-id"
    svc.client = MagicMock()
    svc.client.chat_completion = AsyncMock()
    await svc.interpret(mock_event, AsyncMock())
    svc.client.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_interpretation_service_interpret() -> None:
    svc = InterpretationService()
    mock_event = MagicMock()
    mock_event.ai_interpreted_at = None
    mock_event.id = "test-id"
    mock_event.competitor = MagicMock()
    mock_event.competitor.canonical_name = "Amgen"
    mock_event.event_type = "clinical_trial"
    mock_event.event_subtype = None
    mock_event.development_stage = "phase_3"
    mock_event.indication = "NSCLC"
    mock_event.indication_priority = "HIGH"
    mock_event.country = "US"
    mock_event.region = "NA"
    mock_event.event_date = None
    mock_event.summary = "Test summary"
    mock_event.evidence_excerpt = "Test evidence"
    mock_event.threat_score = 50
    mock_event.traffic_light = "Amber"
    mock_event.verification_status = "verified"
    mock_event.verified_sources_count = 2

    mock_response = {
        "choices": [{"message": {"content": "summary: Test\nwhy_it_matters: Test\nrecommended_action: Test\nconfidence_note: Test"}}]
    }
    svc.client = MagicMock()
    svc.client.chat_completion = AsyncMock(return_value=mock_response)

    await svc.interpret(mock_event, AsyncMock())
    assert mock_event.ai_summary == "Test"
    assert mock_event.ai_why_it_matters == "Test"


@pytest.mark.asyncio
async def test_qa_engine_answer() -> None:
    svc = QAEngine()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    from app.schemas.intelligence import AskRequest
    payload = AskRequest(question="What is the status?")

    # Mock _parse_response to return valid data directly
    with patch.object(svc, "_parse_response", return_value={
        "answer": "Test answer",
        "sources": ["Amgen | trial | NSCLC"],
        "confidence": "0.95",
    }):
        svc.client = MagicMock()
        svc.client.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": "answer: Test answer"}}]
        })

        result = await svc.answer(payload, mock_db)
        assert result.answer == "Test answer"
        assert result.confidence == 0.95
