"""Unit tests for the Indications API route module."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.indications import (
    _generate_insights,
    _vulnerability_styles,
    get_heatmap_email_fragment,
    get_heatmap_json,
    get_heatmap_view,
)
from app.schemas.indication_heatmap import (
    CompetitorColumn,
    HeatmapCell,
    IndicationLandscape,
)


class TestVulnerabilityStyles:
    def test_low_risk(self) -> None:
        color, _bg, label = _vulnerability_styles(30)
        assert label == "Low Risk"
        assert "065f46" in color

    def test_moderate_risk(self) -> None:
        color, _bg, label = _vulnerability_styles(50)
        assert label == "Moderate Risk"
        assert "92400e" in color

    def test_elevated_risk(self) -> None:
        color, _bg, label = _vulnerability_styles(70)
        assert label == "Elevated Risk"
        assert "9a3412" in color

    def test_high_risk(self) -> None:
        color, _bg, label = _vulnerability_styles(90)
        assert label == "High Risk"
        assert "991b1b" in color


class TestGenerateInsights:
    def test_most_active_competitor(self) -> None:
        comp = CompetitorColumn(
            id=uuid4(),
            name="Rival",
            cik=None,
            breadth_score=3,
            depth_score=80,
            focus_type="broad",
        )
        landscape = IndicationLandscape(
            molecule_id=uuid4(),
            molecule_name="Test",
            indications=["A"],
            competitors=[comp],
            matrix=[[]],
            white_space_indications=[],
            contested_indications=[],
            vulnerability_index=50,
            generated_at=datetime.now(UTC),
            total_events_analyzed=1,
        )
        insights = _generate_insights(landscape)
        assert any("Rival" in i for i in insights)

    def test_highest_threat_concentration(self) -> None:
        cell = HeatmapCell(
            competitor_id=uuid4(),
            indication="NSCLC",
            event_count=2,
            avg_threat_score=60.0,
            max_threat_score=70,
            latest_stage="phase_2",
            latest_event_date=datetime.now(UTC),
            heat_score=55,
            stage_abbreviation="P2",
        )
        landscape = IndicationLandscape(
            molecule_id=uuid4(),
            molecule_name="Test",
            indications=["NSCLC"],
            competitors=[],
            matrix=[[cell]],
            white_space_indications=[],
            contested_indications=[],
            vulnerability_index=50,
            generated_at=datetime.now(UTC),
            total_events_analyzed=1,
        )
        insights = _generate_insights(landscape)
        assert any("NSCLC" in i for i in insights)

    def test_white_space_insight(self) -> None:
        landscape = IndicationLandscape(
            molecule_id=uuid4(),
            molecule_name="Test",
            indications=[],
            competitors=[],
            matrix=[],
            white_space_indications=["Melanoma"],
            contested_indications=[],
            vulnerability_index=0,
            generated_at=datetime.now(UTC),
            total_events_analyzed=0,
        )
        insights = _generate_insights(landscape)
        assert any("Melanoma" in i for i in insights)

    def test_empty_landscape(self) -> None:
        landscape = IndicationLandscape(
            molecule_id=uuid4(),
            molecule_name="Test",
            indications=[],
            competitors=[],
            matrix=[],
            white_space_indications=[],
            contested_indications=[],
            vulnerability_index=0,
            generated_at=datetime.now(UTC),
            total_events_analyzed=0,
        )
        insights = _generate_insights(landscape)
        assert insights == []


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_get_heatmap_json(self) -> None:
        mock_landscape = MagicMock()
        with patch(
            "app.api.v1.indications.build_indication_landscape",
            return_value=mock_landscape,
        ):
            result = await get_heatmap_json(molecule_id=uuid4(), db=AsyncMock())
        assert result is mock_landscape

    @pytest.mark.asyncio
    async def test_get_heatmap_view(self) -> None:
        mock_landscape = MagicMock()
        mock_landscape.vulnerability_index = 50
        mock_landscape.indications = ["A"]
        mock_landscape.competitors = []
        mock_landscape.matrix = []
        mock_landscape.white_space_indications = []
        mock_landscape.contested_indications = []

        mock_request = MagicMock()

        with (
            patch(
                "app.api.v1.indications.build_indication_landscape",
                return_value=mock_landscape,
            ),
            patch(
                "app.api.v1.indications.templates.TemplateResponse",
                return_value=MagicMock(status_code=200),
            ),
        ):
            result = await get_heatmap_view(
                request=mock_request,
                molecule_id=uuid4(),
                db=AsyncMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_heatmap_email_fragment_empty(self) -> None:
        mock_landscape = MagicMock()
        mock_landscape.indications = []

        with patch(
            "app.api.v1.indications.build_indication_landscape",
            return_value=mock_landscape,
        ):
            result = await get_heatmap_email_fragment(
                molecule_id=uuid4(),
                db=AsyncMock(),
            )
        assert result.status_code == 200
        assert "No Indication-Level Intelligence Available" in result.body.decode()

    @pytest.mark.asyncio
    async def test_get_heatmap_email_fragment_with_data(self) -> None:
        mock_landscape = MagicMock()
        mock_landscape.indications = ["Melanoma"]
        mock_landscape.molecule_name = "Test"
        mock_landscape.contested_indications = []
        mock_landscape.white_space_indications = []
        mock_landscape.vulnerability_index = 50
        mock_landscape.competitors = []
        mock_landscape.matrix = []

        with patch(
            "app.api.v1.indications.build_indication_landscape",
            return_value=mock_landscape,
        ):
            result = await get_heatmap_email_fragment(
                molecule_id=uuid4(),
                db=AsyncMock(),
            )
        assert result.status_code == 200
        assert "Strategic Landscape by Indication" in result.body.decode()
