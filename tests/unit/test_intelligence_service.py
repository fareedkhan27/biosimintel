from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.config import settings
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
    mock_event.competitor_id = UUID("550e8400-e29b-41d4-a716-446655440002")
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
    mock_event.created_at = None
    mock_event.event_type = "clinical_trial"
    mock_event.id = UUID("550e8400-e29b-41d4-a716-446655440001")

    mock_comp = MagicMock()
    mock_comp.canonical_name = "Rival"
    mock_comp.asset_code = "RV01"
    mock_comp.development_stage = "phase_3"
    mock_comp.status = "active"
    mock_comp.primary_markets = ["US", "EU"]
    mock_comp.launch_window = "2028"
    mock_comp.partnership_status = "solo"
    mock_comp.tier = 1
    mock_comp.created_at = None
    mock_comp.id = UUID("550e8400-e29b-41d4-a716-446655440002")

    mock_result_mol = MagicMock()
    mock_result_mol.scalar_one_or_none.return_value = mock_mol
    mock_result_evt = MagicMock()
    mock_result_evt.scalars.return_value.all.return_value = [mock_event]
    mock_result_comp = MagicMock()
    mock_result_comp.scalars.return_value.all.return_value = [mock_comp]
    mock_result_filing = MagicMock()
    mock_result_filing.scalars.return_value.all.return_value = []

    # 5 execute calls: molecule, events, competitors (financial), filings (financial), competitors (landscape)
    mock_db.execute.side_effect = [
        mock_result_mol,
        mock_result_evt,
        mock_result_comp,  # _build_financial_intelligence queries competitors
        mock_result_filing,  # _build_financial_intelligence queries filings
        mock_result_comp,
    ]

    # Mock the heatmap landscape to avoid extra DB mock setup
    mock_landscape = MagicMock()
    mock_landscape.indications = ["NSCLC"]
    mock_landscape.molecule_name = "TestMol"
    mock_landscape.competitors = [MagicMock(breadth_score=1, name="Rival", focus_type="single")]
    mock_landscape.matrix = [[MagicMock(heat_score=42, indication="NSCLC")]]
    mock_landscape.contested_indications = []
    mock_landscape.white_space_indications = []
    mock_landscape.vulnerability_index = 30
    mock_landscape.model_dump.return_value = {}

    mock_timeline = MagicMock()
    mock_timeline.estimates = []
    mock_timeline.imminent_threats = []
    mock_timeline.model_dump.return_value = {}

    mock_alerts = MagicMock()
    mock_alerts.alerts = []
    mock_alerts.model_dump.return_value = {}

    mock_risk = MagicMock()
    mock_risk.patent_cliffs = []
    mock_risk.model_dump.return_value = {}

    with patch(
        "app.services.intelligence_service.build_indication_landscape",
        return_value=mock_landscape,
    ), patch(
        "app.services.intelligence_service.build_launch_timeline",
        return_value=mock_timeline,
    ), patch(
        "app.services.intelligence_service.detect_threshold_breaches",
        return_value=mock_alerts,
    ), patch(
        "app.services.intelligence_service.calculate_regulatory_risk_weights",
        return_value=mock_risk,
    ):
        payload = EmailBriefingRequest(
            molecule_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            department="market_access",
            format="html",
            since_days=7,
        )
        result = await service.generate_email_briefing(payload, mock_db)

    assert result.html is not None
    assert "NSCLC" in result.html
    assert result.event_count == 1
    assert result.recipient == settings.APAC_EMAIL
    # Competitive landscape should be in the HTML
    assert "Competitive Landscape Overview" in result.html
    assert "Rival" in result.html
    # Indication heatmap should be in the HTML
    assert "Strategic Landscape by Indication" in result.html


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
    mock_result_comp = MagicMock()
    mock_result_comp.scalars.return_value.all.return_value = []
    mock_result_filing = MagicMock()
    mock_result_filing.scalars.return_value.all.return_value = []

    # 5 execute calls: molecule, events, competitors (financial), filings (financial), competitors (landscape)
    mock_db.execute.side_effect = [
        mock_result_mol,
        mock_result_evt,
        mock_result_comp,  # _build_financial_intelligence queries competitors
        mock_result_filing,  # _build_financial_intelligence queries filings
        mock_result_comp,
    ]

    # Mock the heatmap landscape to avoid extra DB mock setup
    mock_landscape = MagicMock()
    mock_landscape.indications = []
    mock_landscape.molecule_name = "TestMol"
    mock_landscape.competitors = []
    mock_landscape.matrix = []
    mock_landscape.contested_indications = []
    mock_landscape.white_space_indications = []
    mock_landscape.vulnerability_index = 0
    mock_landscape.model_dump.return_value = {"test": "data"}

    mock_timeline = MagicMock()
    mock_timeline.estimates = []
    mock_timeline.imminent_threats = []
    mock_timeline.model_dump.return_value = {}

    mock_alerts = MagicMock()
    mock_alerts.alerts = []
    mock_alerts.model_dump.return_value = {}

    mock_risk = MagicMock()
    mock_risk.patent_cliffs = []
    mock_risk.model_dump.return_value = {}

    with patch(
        "app.services.intelligence_service.build_indication_landscape",
        return_value=mock_landscape,
    ), patch(
        "app.services.intelligence_service.build_launch_timeline",
        return_value=mock_timeline,
    ), patch(
        "app.services.intelligence_service.detect_threshold_breaches",
        return_value=mock_alerts,
    ), patch(
        "app.services.intelligence_service.calculate_regulatory_risk_weights",
        return_value=mock_risk,
    ):
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
    assert result.json_payload["competitive_landscape"] == []
    assert result.json_payload["tier_movements"] == []
    assert result.json_payload["indication_landscape"] == {"test": "data"}
    assert result.json_payload["heatmap_insights"] is not None
    assert result.event_count == 0


@pytest.mark.asyncio
async def test_generate_email_briefing_tier_movement() -> None:
    service = IntelligenceService()
    mock_db = AsyncMock()
    mock_mol = MagicMock()
    mock_mol.molecule_name = "TestMol"
    mock_mol.id = UUID("550e8400-e29b-41d4-a716-446655440000")

    mock_comp = MagicMock()
    mock_comp.canonical_name = "Rival"
    mock_comp.asset_code = "RV01"
    mock_comp.development_stage = "phase_3"
    mock_comp.status = "active"
    mock_comp.primary_markets = ["US", "EU"]
    mock_comp.launch_window = "2028"
    mock_comp.partnership_status = "solo"
    mock_comp.tier = 2  # Cached tier differs from computed
    mock_comp.created_at = None
    mock_comp.id = UUID("550e8400-e29b-41d4-a716-446655440002")

    mock_result_mol = MagicMock()
    mock_result_mol.scalar_one_or_none.return_value = mock_mol
    mock_result_evt = MagicMock()
    mock_result_evt.scalars.return_value.all.return_value = []
    mock_result_comp = MagicMock()
    mock_result_comp.scalars.return_value.all.return_value = [mock_comp]
    mock_result_filing = MagicMock()
    mock_result_filing.scalars.return_value.all.return_value = []

    # 5 execute calls: molecule, events, competitors (financial), filings (financial), competitors (landscape)
    mock_db.execute.side_effect = [
        mock_result_mol,
        mock_result_evt,
        mock_result_comp,  # _build_financial_intelligence queries competitors
        mock_result_filing,  # _build_financial_intelligence queries filings
        mock_result_comp,
    ]

    # Mock the heatmap landscape to avoid extra DB mock setup
    mock_landscape = MagicMock()
    mock_landscape.indications = []
    mock_landscape.molecule_name = "TestMol"
    mock_landscape.competitors = []
    mock_landscape.matrix = []
    mock_landscape.contested_indications = []
    mock_landscape.white_space_indications = []
    mock_landscape.vulnerability_index = 0
    mock_landscape.model_dump.return_value = {}

    mock_timeline = MagicMock()
    mock_timeline.estimates = []
    mock_timeline.imminent_threats = []
    mock_timeline.model_dump.return_value = {}

    mock_alerts = MagicMock()
    mock_alerts.alerts = []
    mock_alerts.model_dump.return_value = {}

    mock_risk = MagicMock()
    mock_risk.patent_cliffs = []
    mock_risk.model_dump.return_value = {}

    with patch(
        "app.services.intelligence_service.build_indication_landscape",
        return_value=mock_landscape,
    ), patch(
        "app.services.intelligence_service.build_launch_timeline",
        return_value=mock_timeline,
    ), patch(
        "app.services.intelligence_service.detect_threshold_breaches",
        return_value=mock_alerts,
    ), patch(
        "app.services.intelligence_service.calculate_regulatory_risk_weights",
        return_value=mock_risk,
    ):
        payload = EmailBriefingRequest(
            molecule_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            department="market_access",
            format="json",
            since_days=7,
        )
        result = await service.generate_email_briefing(payload, mock_db)

    assert result.json_payload is not None
    movements = result.json_payload["tier_movements"]
    assert len(movements) == 1
    assert movements[0]["competitor_name"] == "Rival"
    assert movements[0]["from_tier"] == 2
    assert movements[0]["to_tier"] == 1
    # Tier should be updated on the competitor object
    assert mock_comp.tier == 1
    mock_db.commit.assert_awaited_once()


def test_resolve_region_email_india() -> None:
    assert _resolve_region_email("India", None) == settings.APAC_EMAIL


def test_resolve_region_email_us() -> None:
    assert _resolve_region_email("United States", None) == settings.NA_EMAIL
    assert _resolve_region_email("US", None) == settings.NA_EMAIL


def test_resolve_region_email_eu() -> None:
    assert _resolve_region_email("Germany", None) == settings.EMEA_EMAIL
    assert _resolve_region_email("France", None) == settings.EMEA_EMAIL
    assert _resolve_region_email("EU", None) == settings.EMEA_EMAIL


def test_resolve_region_email_unknown() -> None:
    assert _resolve_region_email("Mars", None) == settings.EXECUTIVE_EMAIL
