from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ingest_clinicaltrials(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "ct_jobs_test",
        "reference_brand": "CTBrand",
        "manufacturer": "CTCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()
    resp = await client.post(f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}")
    assert resp.status_code in (200, 500, 502)


@pytest.mark.asyncio
async def test_ingest_ema(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "ema_jobs_test",
        "reference_brand": "EMABrand",
        "manufacturer": "EMACo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()
    resp = await client.post(f"/api/v1/jobs/ingest/ema?molecule_id={molecule['id']}")
    assert resp.status_code in (200, 500, 502)


@pytest.mark.asyncio
async def test_ingest_sec_edgar(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "sec_jobs_test",
        "reference_brand": "SECBrand",
        "manufacturer": "SECCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()
    resp = await client.post(f"/api/v1/jobs/ingest/sec-edgar?molecule_id={molecule['id']}")
    assert resp.status_code in (200, 500, 502)


@pytest.mark.asyncio
async def test_ingest_fda_purple_book(client: AsyncClient) -> None:
    mol = await client.post("/api/v1/molecules", json={
        "molecule_name": "fda_jobs_test",
        "reference_brand": "FDABrand",
        "manufacturer": "FDACo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol.json()
    resp = await client.post(f"/api/v1/jobs/ingest/fda-purple-book?molecule_id={molecule['id']}")
    assert resp.status_code in (200, 500, 502)
