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
async def test_red_alert_returns_red_events_within_24h(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Red alert webhook returns verified Red events from last 24 hours."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="red_alert_mol",
        reference_brand="RedBrand",
        manufacturer="RedCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="RedRival",
        tier=1,
        asset_code="RR01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="company_ir",
        source_type="press_release",
        external_id="PR001",
        title="Red PR",
        url="https://example.com/red",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="press_release",
        development_stage="approved",
        indication="NSCLC",
        country="India",
        threat_score=88,
        traffic_light="Red",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.post("/api/v1/webhooks/red-alert")
    assert resp.status_code == 200
    data = resp.json()

    assert data["alert_count"] == 1
    assert len(data["alerts"]) == 1
    alert = data["alerts"][0]
    assert alert["event"]["traffic_light"] == "Red"
    assert alert["routing"]["region"] == "India"
    assert alert["routing"]["recipient"] == "apac-team@example.com"
    assert alert["routing"]["from_email"] == "intelligence@biosimintel.com"
    assert "checked_since" in data


@pytest.mark.asyncio
async def test_red_alert_excludes_old_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Red alert excludes Red events older than 24 hours."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="old_red_mol",
        reference_brand="OldBrand",
        manufacturer="OldCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="OldRival",
        tier=1,
        asset_code="OR01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="company_ir",
        source_type="press_release",
        external_id="PR002",
        title="Old Red PR",
        url="https://example.com/old",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="press_release",
        threat_score=90,
        traffic_light="Red",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.post("/api/v1/webhooks/red-alert")
    assert resp.status_code == 200
    data = resp.json()

    assert data["alert_count"] == 0
    assert data["alerts"] == []


@pytest.mark.asyncio
async def test_red_alert_excludes_non_red_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Red alert excludes Amber and Green events."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="amber_mol",
        reference_brand="AmberBrand",
        manufacturer="AmberCo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="AmberRival",
        tier=2,
        asset_code="AR01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="clinicaltrials_gov",
        source_type="clinical_trial",
        external_id="NCT44444444",
        title="Amber Trial",
        url="https://example.com/amber",
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
        threat_score=50,
        traffic_light="Amber",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.post("/api/v1/webhooks/red-alert")
    assert resp.status_code == 200
    data = resp.json()

    assert data["alert_count"] == 0
    assert data["alerts"] == []


@pytest.mark.asyncio
async def test_red_alert_regional_routing_na(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """US Red events route to NA_EMAIL."""
    molecule = Molecule(
        id=uuid4(),
        molecule_name="na_red_mol",
        reference_brand="NABrand",
        manufacturer="NACo",
    )
    db_session.add(molecule)
    await db_session.flush()

    competitor = Competitor(
        id=uuid4(),
        molecule_id=molecule.id,
        canonical_name="NARival",
        tier=1,
        asset_code="NA01",
    )
    db_session.add(competitor)
    await db_session.flush()

    doc = SourceDocument(
        id=uuid4(),
        source_name="company_ir",
        source_type="press_release",
        external_id="PR003",
        title="NA Red PR",
        url="https://example.com/na",
        molecule_id=molecule.id,
    )
    db_session.add(doc)
    await db_session.flush()

    event = Event(
        id=uuid4(),
        molecule_id=molecule.id,
        source_document_id=doc.id,
        competitor_id=competitor.id,
        event_type="press_release",
        country="United States",
        threat_score=92,
        traffic_light="Red",
        verification_status="verified",
        verification_confidence=0.95,
        verified_sources_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    await db_session.commit()

    resp = await client.post("/api/v1/webhooks/red-alert")
    assert resp.status_code == 200
    data = resp.json()

    assert data["alert_count"] == 1
    assert data["alerts"][0]["routing"]["recipient"] == "na-team@example.com"
    assert data["alerts"][0]["routing"]["region"] == "United States"
