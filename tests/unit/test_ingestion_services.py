from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ingestion.clinicaltrials import ClinicalTrialsService
from app.services.ingestion.press_release import PressReleaseService


@pytest.mark.asyncio
async def test_clinicaltrials_service_init() -> None:
    svc = ClinicalTrialsService()
    assert svc.base_url == "https://clinicaltrials.gov/api/v2/studies"
    await svc.close()


@pytest.mark.asyncio
async def test_press_release_ingest_mock() -> None:
    svc = PressReleaseService()
    mock_db = AsyncMock()
    mock_existing_result = MagicMock()
    mock_existing_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_existing_result
    mock_molecule = MagicMock()
    mock_molecule.id = "mock-id"
    mock_molecule.molecule_name = "test"

    await svc.ingest("Test text", "https://example.com", mock_molecule, mock_db)
    assert mock_db.add.called
    assert mock_db.flush.called
