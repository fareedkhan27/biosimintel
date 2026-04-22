from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_intelligence_briefing(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "briefing_test",
        "reference_brand": "BriefBrand",
        "manufacturer": "BriefCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()

    payload = {
        "molecule_id": molecule["id"],
        "departments": ["market_access"],
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "departments" in data
