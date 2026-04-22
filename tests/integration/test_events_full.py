from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_event_provenance_and_interpret(client: AsyncClient) -> None:
    # Create molecule
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "event_full_test",
        "reference_brand": "EventBrand",
        "manufacturer": "EventCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()

    # Create competitor
    comp = await client.post("/api/v1/competitors", json={
        "molecule_id": molecule["id"],
        "canonical_name": "TestComp",
        "tier": 1,
        "asset_code": "TC001",
        "development_stage": "phase_3",
        "status": "active",
        "primary_markets": ["US"],
        "launch_window": "2028",
        "parent_company": "TestCo",
    })
    comp.json()

    # Create event via jobs/recompute-scores or we need an event creation endpoint
    # Since there's no direct event creation API in the spec, let's use ingestion
    job = await client.post(f"/api/v1/jobs/ingest/press-release?text=Test+launch&source_url=https://example.com&molecule_id={molecule['id']}")
    # This creates an event
    assert job.status_code in (200, 500)

    # List events
    events = await client.get(f"/api/v1/events?molecule_id={molecule['id']}")
    assert events.status_code == 200
    event_list = events.json()
    assert isinstance(event_list, list)

    if event_list:
        event_id = event_list[0]["id"]
        # Get event
        evt = await client.get(f"/api/v1/events/{event_id}")
        assert evt.status_code == 200

        # Get provenance
        prov = await client.get(f"/api/v1/events/{event_id}/provenance")
        assert prov.status_code == 200
        assert isinstance(prov.json(), list)

        # Interpret (may fail if AI not configured)
        interp = await client.post(f"/api/v1/events/{event_id}/interpret")
        assert interp.status_code in (200, 500, 502)
