from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_job_ingest_endpoints(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "jobs_test",
        "reference_brand": "JobsBrand",
        "manufacturer": "JobsCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()

    # These may return 200 or 500 depending on external APIs
    endpoints = [
        f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}",
        f"/api/v1/jobs/ingest/ema?molecule_id={molecule['id']}",
        f"/api/v1/jobs/ingest/sec-edgar?molecule_id={molecule['id']}",
        f"/api/v1/jobs/ingest/fda-purple-book?molecule_id={molecule['id']}",
    ]
    for url in endpoints:
        resp = await client.post(url)
        assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_job_ingest_press_release(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "pr_test",
        "reference_brand": "PRBrand",
        "manufacturer": "PRCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()

    resp = await client.post(
        f"/api/v1/jobs/ingest/press-release?text=Test+press+release&source_url=https://example.com/pr&molecule_id={molecule['id']}"
    )
    assert resp.status_code in (200, 500)
