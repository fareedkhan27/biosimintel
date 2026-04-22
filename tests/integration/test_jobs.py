from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_recompute_scores(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "recompute_test",
        "reference_brand": "RecomputeBrand",
        "manufacturer": "RecomputeCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    molecule = mol_resp.json()

    response = await client.post(f"/api/v1/jobs/recompute-scores?molecule_id={molecule['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "recompute_scores"
