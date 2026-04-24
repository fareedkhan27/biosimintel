from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule
from app.models.source_document import SourceDocument


@pytest.mark.asyncio
async def test_email_briefing_html_format(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Email briefing endpoint returns rendered HTML with all sections."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="email_test_mol",
        reference_brand="EmailBrand",
        manufacturer="EmailCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="EmailRival",
        tier=1,
        asset_code="ER01",
        development_stage="phase_3",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT11111111",
        title="Email Trial",
        url="https://example.com/email",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        development_stage="phase_3",
        indication="NSCLC",
        country="India",
        event_date=datetime(2025, 3, 1, tzinfo=UTC),
        summary="Phase 3 NSCLC trial in India",
        threat_score=85,
        traffic_light="Red",
        verification_status="verified",
        verification_confidence=0.99,
        verified_sources_count=1,
        ai_why_it_matters="India represents a high-growth biosimilar market.",
        ai_recommended_action="Monitor pricing signals closely.",
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "department": "market_access",
        "format": "html",
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing/email", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["html"] is not None
    assert "EmailRival" in data["html"]
    assert "Phase 3 NSCLC trial in India" in data["html"]
    assert "India" in data["html"]
    assert "OPEN" in data["html"]
    assert data["event_count"] == 1
    assert data["recipient"] is not None
    assert data["from_email"] == "intelligence@biosimintel.com"
    assert "Weekly Briefing: email_test_mol" in data["subject"]
    assert data["region"] == "India"

    # Threat interpretation fields should be present in HTML
    assert "Moderate" in data["html"] or "Critical" in data["html"] or "High" in data["html"]
    assert "Threat Level Guide" in data["html"]


@pytest.mark.asyncio
async def test_email_briefing_json_format(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Email briefing endpoint returns structured JSON when format=json."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="json_test_mol",
        reference_brand="JsonBrand",
        manufacturer="JsonCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="JsonRival",
        tier=2,
        asset_code="JR01",
        development_stage="phase_2",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT22222222",
        title="Json Trial",
        url="https://example.com/json",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        development_stage="phase_2",
        indication="Melanoma",
        country="United States",
        threat_score=55,
        traffic_light="Amber",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "department": "medical_affairs",
        "format": "json",
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing/email", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["json_payload"] is not None
    assert data["html"] is None
    assert data["json_payload"]["executive_summary"] is not None
    assert len(data["json_payload"]["events"]) == 1
    assert data["json_payload"]["events"][0]["competitor_name"] == "JsonRival"
    assert data["event_count"] == 1
    assert data["region"] == "United States"

    # Threat interpretation fields in JSON payload
    event = data["json_payload"]["events"][0]
    assert "threat_label" in event
    assert "threat_color" in event
    assert "threat_explanation" in event
    assert "threat_guide" in data["json_payload"]


@pytest.mark.asyncio
async def test_email_briefing_empty_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Email briefing for molecule with no events returns zero count and empty HTML."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="empty_email_mol",
        reference_brand="EmptyBrand",
        manufacturer="EmptyCo",
    )
    db_session.add(molecule)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "department": "market_access",
        "format": "html",
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing/email", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["event_count"] == 0
    assert "No significant competitive activity detected" in data["html"]
    assert data["region"] == "Global"


@pytest.mark.asyncio
async def test_email_briefing_nonexistent_molecule_returns_404(
    client: AsyncClient,
) -> None:
    """Email briefing for missing molecule returns 404."""
    payload = {
        "molecule_id": "550e8400-e29b-41d4-a716-446655440999",
        "department": "market_access",
        "format": "html",
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing/email", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_email_briefing_regional_routing_eu(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EU events route to EMEA_EMAIL."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="eu_routing_mol",
        reference_brand="EUBrand",
        manufacturer="EUCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="EURival",
        tier=1,
        asset_code="EU01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT33333333",
        title="EU Trial",
        url="https://example.com/eu",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        country="Germany",
        threat_score=60,
        traffic_light="Amber",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "department": "market_access",
        "format": "html",
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing/email", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipient"] == "emea-team@example.com"
