"""Unit tests for the indication heatmap analytics engine."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.indication_heatmap import IndicationLandscape
from app.services.indication_heatmap import (
    _compute_heat_score,
    _stage_abbreviation,
    _stage_weight,
    build_indication_landscape,
)


class TestHelpers:
    """Tests for standalone helper functions."""

    def test_stage_weight_preclinical(self) -> None:
        assert _stage_weight("preclinical") == 5
        assert _stage_weight("pre_clinical") == 5

    def test_stage_weight_phase3(self) -> None:
        assert _stage_weight("phase3") == 50
        assert _stage_weight("phase_3") == 50

    def test_stage_weight_approved(self) -> None:
        assert _stage_weight("approved") == 100
        assert _stage_weight("launched") == 100

    def test_stage_weight_unknown(self) -> None:
        assert _stage_weight(None) == 5
        assert _stage_weight("unknown_stage") == 5

    def test_stage_abbreviation(self) -> None:
        assert _stage_abbreviation("phase_1") == "P1"
        assert _stage_abbreviation("phase_3") == "P3"
        assert _stage_abbreviation("bla") == "BLA"
        assert _stage_abbreviation("approved") == "AP"
        assert _stage_abbreviation(None) == "PC"

    def test_compute_heat_score(self) -> None:
        # Low activity, low threat, early stage
        assert _compute_heat_score(10.0, 1, "preclinical") < 30
        # High activity, high threat, late stage
        assert _compute_heat_score(80.0, 5, "approved") == 100
        # Mid-range
        score = _compute_heat_score(50.0, 3, "phase2")
        assert 40 <= score <= 80


class TestBuildIndicationLandscape:
    """Tests for the core landscape builder."""

    @pytest.mark.asyncio
    async def test_molecule_not_found(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception):  # noqa: B017
            await build_indication_landscape(uuid4(), mock_db)

    @pytest.mark.asyncio
    async def test_empty_events(self) -> None:
        mock_db = AsyncMock()
        mock_mol = MagicMock()
        mock_mol.molecule_name = "TestMol"
        mock_mol.indications = None

        mock_result_mol = MagicMock()
        mock_result_mol.scalar_one_or_none.return_value = mock_mol
        mock_result_evt = MagicMock()
        mock_result_evt.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result_mol, mock_result_evt]

        result = await build_indication_landscape(uuid4(), mock_db)
        assert isinstance(result, IndicationLandscape)
        assert result.molecule_name == "TestMol"
        assert result.indications == []
        assert result.competitors == []
        assert result.matrix == []
        assert result.vulnerability_index == 0
        assert result.total_events_analyzed == 0

    @pytest.mark.asyncio
    async def test_single_event_single_competitor(self) -> None:
        """One event creates one cell in the matrix."""
        mock_db = AsyncMock()
        mock_mol = MagicMock()
        mock_mol.molecule_name = "TestMol"
        mock_mol.indications = None

        comp_id = uuid4()
        mock_event = MagicMock()
        mock_event.indication = "Melanoma"
        mock_event.competitor_id = comp_id
        mock_event.threat_score = 50
        mock_event.development_stage = "phase_2"
        mock_event.created_at = datetime.now(UTC)

        mock_comp = MagicMock()
        mock_comp.id = comp_id
        mock_comp.canonical_name = "Rival"
        mock_comp.cik = None

        mock_result_mol = MagicMock()
        mock_result_mol.scalar_one_or_none.return_value = mock_mol
        mock_result_evt = MagicMock()
        mock_result_evt.scalars.return_value.all.return_value = [mock_event]
        mock_result_comp = MagicMock()
        mock_result_comp.scalars.return_value.all.return_value = [mock_comp]

        mock_db.execute.side_effect = [
            mock_result_mol,
            mock_result_evt,
            mock_result_comp,
        ]

        result = await build_indication_landscape(uuid4(), mock_db)
        assert result.indications == ["Melanoma"]
        assert len(result.competitors) == 1
        assert result.competitors[0].name == "Rival"
        assert result.matrix[0][0] is not None
        assert result.matrix[0][0].event_count == 1
        assert result.matrix[0][0].heat_score > 0

    @pytest.mark.asyncio
    async def test_white_space_from_configured_indications(self) -> None:
        """Indications configured on molecule but with no events are white space."""
        mock_db = AsyncMock()
        mock_mol = MagicMock()
        mock_mol.molecule_name = "TestMol"
        mock_mol.indications = {"NSCLC": "high", "Melanoma": "high"}

        mock_event = MagicMock()
        mock_event.indication = "Melanoma"
        mock_event.competitor_id = uuid4()
        mock_event.threat_score = 30
        mock_event.development_stage = "phase_1"
        mock_event.created_at = datetime.now(UTC)

        mock_comp = MagicMock()
        mock_comp.id = mock_event.competitor_id
        mock_comp.canonical_name = "Rival"
        mock_comp.cik = None

        mock_result_mol = MagicMock()
        mock_result_mol.scalar_one_or_none.return_value = mock_mol
        mock_result_evt = MagicMock()
        mock_result_evt.scalars.return_value.all.return_value = [mock_event]
        mock_result_comp = MagicMock()
        mock_result_comp.scalars.return_value.all.return_value = [mock_comp]

        mock_db.execute.side_effect = [
            mock_result_mol,
            mock_result_evt,
            mock_result_comp,
        ]

        result = await build_indication_landscape(uuid4(), mock_db)
        assert "NSCLC" in result.white_space_indications
        assert "Melanoma" not in result.white_space_indications

    @pytest.mark.asyncio
    async def test_contested_indications(self) -> None:
        """An indication with 3+ competitors is contested."""
        mock_db = AsyncMock()
        mock_mol = MagicMock()
        mock_mol.molecule_name = "TestMol"
        mock_mol.indications = None

        events = []
        comps = []
        for i in range(3):
            comp_id = uuid4()
            evt = MagicMock()
            evt.indication = "NSCLC"
            evt.competitor_id = comp_id
            evt.threat_score = 40
            evt.development_stage = "phase_2"
            evt.created_at = datetime.now(UTC)
            events.append(evt)

            comp = MagicMock()
            comp.id = comp_id
            comp.canonical_name = f"Rival-{i}"
            comp.cik = None
            comps.append(comp)

        mock_result_mol = MagicMock()
        mock_result_mol.scalar_one_or_none.return_value = mock_mol
        mock_result_evt = MagicMock()
        mock_result_evt.scalars.return_value.all.return_value = events
        mock_result_comp = MagicMock()
        mock_result_comp.scalars.return_value.all.return_value = comps

        mock_db.execute.side_effect = [
            mock_result_mol,
            mock_result_evt,
            mock_result_comp,
        ]

        result = await build_indication_landscape(uuid4(), mock_db)
        assert "NSCLC" in result.contested_indications
        assert result.vulnerability_index > 0

    @pytest.mark.asyncio
    async def test_competitor_focus_types(self) -> None:
        """Competitors are classified by breadth of indications."""
        mock_db = AsyncMock()
        mock_mol = MagicMock()
        mock_mol.molecule_name = "TestMol"
        mock_mol.indications = None

        comp_id = uuid4()
        events = []
        for ind in ["A", "B", "C", "D", "E"]:
            evt = MagicMock()
            evt.indication = ind
            evt.competitor_id = comp_id
            evt.threat_score = 20
            evt.development_stage = "phase_1"
            evt.created_at = datetime.now(UTC)
            events.append(evt)

        mock_comp = MagicMock()
        mock_comp.id = comp_id
        mock_comp.canonical_name = "BroadRival"
        mock_comp.cik = None

        mock_result_mol = MagicMock()
        mock_result_mol.scalar_one_or_none.return_value = mock_mol
        mock_result_evt = MagicMock()
        mock_result_evt.scalars.return_value.all.return_value = events
        mock_result_comp = MagicMock()
        mock_result_comp.scalars.return_value.all.return_value = [mock_comp]

        mock_db.execute.side_effect = [
            mock_result_mol,
            mock_result_evt,
            mock_result_comp,
        ]

        result = await build_indication_landscape(uuid4(), mock_db)
        assert result.competitors[0].focus_type == "broad"
        assert result.competitors[0].breadth_score == 5
