from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_molecule(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "test_molecule",
        "reference_brand": "TestBrand",
        "manufacturer": "TestCo",
        "search_terms": ["test"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    response = await client.post("/api/v1/molecules", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["molecule_name"] == "test_molecule"

    get_response = await client.get(f"/api/v1/molecules/{created['id']}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["molecule_name"] == "test_molecule"


@pytest.mark.asyncio
async def test_list_molecules(client: AsyncClient) -> None:
    response = await client.get("/api/v1/molecules")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_update_molecule(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "update_test",
        "reference_brand": "UpdateBrand",
        "manufacturer": "UpdateCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    create_resp = await client.post("/api/v1/molecules", json=payload)
    created = create_resp.json()

    patch_resp = await client.patch(
        f"/api/v1/molecules/{created['id']}",
        json={"manufacturer": "PatchedCo"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["manufacturer"] == "PatchedCo"
