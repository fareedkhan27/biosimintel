from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_competitor(client: AsyncClient) -> None:
    # First create a molecule
    molecule_payload = {
        "molecule_name": "comp_test",
        "reference_brand": "CompBrand",
        "manufacturer": "CompCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=molecule_payload)
    molecule = mol_resp.json()

    payload = {
        "molecule_id": molecule["id"],
        "canonical_name": "TestComp",
        "tier": 1,
        "asset_code": "TC001",
        "development_stage": "phase_3",
        "status": "active",
        "primary_markets": ["US"],
        "launch_window": "2028",
        "parent_company": "TestCo",
    }
    response = await client.post("/api/v1/competitors", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["canonical_name"] == "TestComp"

    get_response = await client.get(f"/api/v1/competitors/{created['id']}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["canonical_name"] == "TestComp"
