"""Integration tests for the Indication Heatmap API endpoints."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule


@pytest.mark.asyncio
async def test_heatmap_json_endpoint(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "heatmap_json_test",
        "reference_brand": "HeatBrand",
        "manufacturer": "HeatCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    assert mol_resp.status_code == 201
    molecule = mol_resp.json()
    molecule_id = molecule["id"]

    resp = await client.get(
        f"/api/v1/intelligence/heatmap?molecule_id={molecule_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["molecule_id"] == molecule_id
    assert data["molecule_name"] == "heatmap_json_test"
    assert "indications" in data
    assert "competitors" in data
    assert "matrix" in data
    assert "white_space_indications" in data
    assert "contested_indications" in data
    assert "vulnerability_index" in data
    assert "generated_at" in data
    assert "total_events_analyzed" in data


@pytest.mark.asyncio
async def test_heatmap_view_endpoint(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "heatmap_view_test",
        "reference_brand": "HeatBrand",
        "manufacturer": "HeatCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    assert mol_resp.status_code == 201
    molecule = mol_resp.json()
    molecule_id = molecule["id"]

    resp = await client.get(
        f"/api/v1/intelligence/heatmap/view?molecule_id={molecule_id}"
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Competitive Landscape" in html


@pytest.mark.asyncio
async def test_heatmap_email_fragment_endpoint(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "heatmap_email_test",
        "reference_brand": "HeatBrand",
        "manufacturer": "HeatCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    assert mol_resp.status_code == 201
    molecule = mol_resp.json()
    molecule_id = molecule["id"]

    resp = await client.get(
        f"/api/v1/intelligence/heatmap/email-fragment?molecule_id={molecule_id}"
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    # Empty-state fragment when no indication data
    assert "No Indication-Level Intelligence Available" in html


@pytest.mark.asyncio
async def test_heatmap_with_data(client: AsyncClient, db_session: AsyncSession) -> None:
    """Seed events with indication data and verify full rendering path."""
    molecule = Molecule(
        molecule_name="heatmap_data_test",
        reference_brand="HeatBrand",
        manufacturer="HeatCo",
    )
    db_session.add(molecule)
    await db_session.commit()
    await db_session.refresh(molecule)

    competitor = Competitor(
        molecule_id=molecule.id,
        canonical_name="RivalCo",
        tier=1,
    )
    db_session.add(competitor)
    await db_session.commit()
    await db_session.refresh(competitor)

    event = Event(
        molecule_id=molecule.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        development_stage="phase_2",
        indication="Melanoma",
        threat_score=55,
    )
    db_session.add(event)
    await db_session.commit()

    # JSON endpoint
    resp = await client.get(
        f"/api/v1/intelligence/heatmap?molecule_id={molecule.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["molecule_id"] == str(molecule.id)
    assert "Melanoma" in data["indications"]
    assert len(data["competitors"]) == 1
    assert data["competitors"][0]["name"] == "RivalCo"
    assert data["matrix"][0][0] is not None
    assert data["matrix"][0][0]["heat_score"] > 0

    # HTML view endpoint
    resp = await client.get(
        f"/api/v1/intelligence/heatmap/view?molecule_id={molecule.id}"
    )
    assert resp.status_code == 200
    html = resp.text
    assert "Indication Battlefield" in html
    assert "Vulnerability Index" in html

    # Email fragment endpoint (non-empty path)
    resp = await client.get(
        f"/api/v1/intelligence/heatmap/email-fragment?molecule_id={molecule.id}"
    )
    assert resp.status_code == 200
    html = resp.text
    assert "Strategic Landscape by Indication" in html
    assert "Melanoma" in html


@pytest.mark.asyncio
async def test_heatmap_json_unknown_molecule(client: AsyncClient) -> None:
    fake_id = uuid4()
    resp = await client.get(
        f"/api/v1/intelligence/heatmap?molecule_id={fake_id}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heatmap_email_fragment_empty_state(client: AsyncClient) -> None:
    payload = {
        "molecule_name": "heatmap_empty_test",
        "reference_brand": "HeatBrand",
        "manufacturer": "HeatCo",
        "search_terms": [],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    }
    mol_resp = await client.post("/api/v1/molecules", json=payload)
    assert mol_resp.status_code == 201
    molecule = mol_resp.json()
    molecule_id = molecule["id"]

    resp = await client.get(
        f"/api/v1/intelligence/heatmap/email-fragment?molecule_id={molecule_id}"
    )
    assert resp.status_code == 200
    html = resp.text
    # Empty-state fragment when no indication data
    assert "No Indication-Level Intelligence Available" in html
