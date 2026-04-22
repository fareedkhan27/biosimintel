from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.schemas.intelligence import BriefingRequest, EmailBriefingRequest
from app.services.intelligence_service import (
    IntelligenceService,
    _resolve_region_email,
)


@pytest.mark.asyncio
async def test_generate_briefing() -> None:
    service = IntelligenceService()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(
        molecule_name="test",
        id="mock-id",
    )
    mock_db.execute.return_value = mock_result

    payload = BriefingRequest(
        molecule_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        departments=["market_access"],
        since_days=7,
    )
    result = await service.generate_briefing(payload, mock_db)
    assert result.molecule_id == payload.molecule_id
    assert "market_access" in result.departments


@pytest.mark.asyncio
async def test_generate_email_briefing_html() -> None:
    service = IntelligenceService()
    mock_db = AsyncMock()
    mock_mol = MagicMock()
    mock_mol.molecule_name = "TestMol"
    mock_mol.id = UUID("550e8400-e29b-41d4-a716-446655440000")

    mock_event = MagicMock()
    mock_event.competitor = MagicMock()
    mock_event.competitor.canonical_name = "Rival"
    mock_event.competitor.asset_code = "RV01"
    mock_event.development_stage = "phase_3"
    mock_event.indication = "NSCLC"
    mock_event.country = "India"
    mock_event.region = None
    mock_event.threat_score = 80
    mock_event.traffic_light = "Red"
    mock_event.summary = "Trial summary"
    mock_event.ai_why_it_matters = "It matters"
    mock_event.ai_recommended_action = "Do something"
    mock_event.event_date = None
    mock_event.id = UUID("550e8400-e29b-41d4-a716-446655440001")

    mock_result_mol = MagicMock()
    mock_result_mol.scalar_one_or_none.return_value = mock_mol
    mock_result_evt = MagicMock()
    mock_result_evt.scalars.return_value.all.return_value = [mock_event]

    mock_db.execute.side_effect = [mock_result_mol, mock_result_evt]

    payload = EmailBriefingRequest(
        molecule_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        department="market_access",
        format="html",
        since_days=7,
    )
    result = await service.generate_email_briefing(payload, mock_db)
    assert result.html is not None
    assert "Trial summary" in result.html
    assert result.event_count == 1
    assert result.recipient == "apac-team@example.com"


@pytest.mark.asyncio
async def test_generate_email_briefing_json() -> None:
    service = IntelligenceService()
    mock_db = AsyncMock()
    mock_mol = MagicMock()
    mock_mol.molecule_name = "TestMol"
    mock_mol.id = UUID("550e8400-e29b-41d4-a716-446655440000")

    mock_result_mol = MagicMock()
    mock_result_mol.scalar_one_or_none.return_value = mock_mol
    mock_result_evt = MagicMock()
    mock_result_evt.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_mol, mock_result_evt]

    payload = EmailBriefingRequest(
        molecule_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        department="medical_affairs",
        format="json",
        since_days=7,
    )
    result = await service.generate_email_briefing(payload, mock_db)
    assert result.json_payload is not None
    assert result.html is None
    assert result.json_payload["executive_summary"] is not None
    assert result.event_count == 0


def test_resolve_region_email_india() -> None:
    assert _resolve_region_email("India", None) == "apac-team@example.com"


def test_resolve_region_email_us() -> None:
    assert _resolve_region_email("United States", None) == "na-team@example.com"
    assert _resolve_region_email("US", None) == "na-team@example.com"


def test_resolve_region_email_eu() -> None:
    assert _resolve_region_email("Germany", None) == "emea-team@example.com"
    assert _resolve_region_email("France", None) == "emea-team@example.com"
    assert _resolve_region_email("EU", None) == "emea-team@example.com"


def test_resolve_region_email_unknown() -> None:
    assert _resolve_region_email("Mars", None) == "exec-team@example.com"
