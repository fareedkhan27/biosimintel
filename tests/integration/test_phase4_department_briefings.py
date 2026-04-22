from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.event import Event
from app.models.molecule import Molecule
from app.models.source_document import SourceDocument


@pytest.mark.asyncio
async def test_briefing_returns_structure_with_verified_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Briefing endpoint returns executive_summary, market_sections, milestones."""
    # Create molecule
    molecule = Molecule(
        id=uuid4(),
        molecule_name="briefing_mol",
        reference_brand="BriefBrand",
        manufacturer="BriefCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    # Create competitor
    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="RivalCo",
        tier=1,
        asset_code="RC01",
        development_stage="phase_3",
    )
    db_session.add(competitor)
    await db_session.flush()

    # Create source document
    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT12345678",
        title="Test Trial",
        url="https://clinicaltrials.gov/ct2/show/NCT12345678",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    # Create verified event
    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        development_stage="phase_3",
        indication="NSCLC",
        country="United States",
        event_date=datetime(2025, 1, 15, tzinfo=UTC),
        summary="Phase 3 trial in NSCLC",
        threat_score=75,
        traffic_light="Red",
        verification_status="verified",
        verification_confidence=0.99,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "departments": ["market_access", "medical_affairs"],
        "since_days": 30,
    }
    resp = await client.post("/api/v1/intelligence/briefing", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["molecule_id"] == str(molecule.id)
    assert "departments" in data
    assert "market_access" in data["departments"]
    assert "medical_affairs" in data["departments"]

    for dept in ["market_access", "medical_affairs"]:
        section = data["departments"][dept]
        assert "executive_summary" in section
        assert "market_sections" in section
        assert "milestones" in section
        assert len(section["market_sections"]) == 1
        assert section["market_sections"][0]["competitor"] == "RivalCo"
        assert section["market_sections"][0]["threat_score"] == 75
        assert len(section["milestones"]) == 1
        assert "RivalCo" in section["milestones"][0]["competitor"]


@pytest.mark.asyncio
async def test_briefing_with_no_events_returns_empty_sections(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Briefing for molecule with no events returns empty market_sections and milestones."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="empty_briefing_mol",
        reference_brand="EmptyBrand",
        manufacturer="EmptyCo",
    )
    db_session.add(molecule)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "departments": ["market_access"],
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    section = data["departments"]["market_access"]
    assert "No significant competitive activity detected" in section["executive_summary"]
    assert section["market_sections"] == []
    assert section["milestones"] == []


@pytest.mark.asyncio
async def test_briefing_since_days_filtering(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Briefing respects since_days and excludes old events."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="since_filter_mol",
        reference_brand="SinceBrand",
        manufacturer="SinceCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="OldComp",
        tier=2,
        asset_code="OC01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT99999999",
        title="Old Trial",
        url="https://example.com/old",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    # Event created 60 days ago
    old_event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="clinical_trial",
        development_stage="phase_2",
        indication="RCC",
        country="US",
        summary="Old trial",
        threat_score=45,
        traffic_light="Amber",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC) - timedelta(days=60),
    )
    db_session.add(old_event)
    await db_session.commit()

    payload = {
        "molecule_id": str(molecule.id),
        "departments": ["market_access"],
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    section = data["departments"]["market_access"]
    # Old event should be excluded by since_days filter
    assert section["market_sections"] == []
    assert section["milestones"] == []
    assert "No significant competitive activity detected" in section["executive_summary"]


@pytest.mark.asyncio
async def test_briefing_nonexistent_molecule_returns_404(client: AsyncClient) -> None:
    """Briefing for nonexistent molecule returns 404."""
    payload = {
        "molecule_id": "550e8400-e29b-41d4-a716-446655440999",
        "departments": ["market_access"],
        "since_days": 7,
    }
    resp = await client.post("/api/v1/intelligence/briefing", json=payload)
    assert resp.status_code == 404
    assert "Molecule" in resp.json()["detail"]
