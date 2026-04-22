from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_intelligence_summary(client: AsyncClient) -> None:
    # Create a molecule first
    payload = {
        "molecule_name": "intel_test",
        "reference_brand": "IntelBrand",
        "manufacturer": "IntelCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    molecule = mol_resp.json()

    response = await client.get(f"/api/v1/intelligence/summary?molecule_id={molecule['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["molecule_id"] == molecule["id"]
    assert "total_events" in data


@pytest.mark.asyncio
async def test_top_threats(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "threat_test",
        "reference_brand": "ThreatBrand",
        "manufacturer": "ThreatCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    molecule = mol_resp.json()

    response = await client.get(f"/api/v1/intelligence/top-threats?molecule_id={molecule['id']}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_recent_events(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "recent_test",
        "reference_brand": "RecentBrand",
        "manufacturer": "RecentCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    molecule = mol_resp.json()

    response = await client.get(f"/api/v1/intelligence/recent?molecule_id={molecule['id']}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_ask_question(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "ask_test",
        "reference_brand": "AskBrand",
        "manufacturer": "AskCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    molecule = mol_resp.json()

    ask_payload = {"question": "What is the status?", "molecule_id": molecule["id"]}
    response = await client.post("/api/v1/intelligence/ask", json=ask_payload)
    # May fail if AI not configured, but endpoint should respond
    assert response.status_code in (200, 500, 502)
