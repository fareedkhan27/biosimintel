from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.models.data_provenance import DataProvenance
from app.models.event import Event
from app.models.source_document import SourceDocument
from app.services.engine.scoring import ScoringEngine

SAMPLE_CLINICALTRIALS_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT04201276",
                    "briefTitle": "A Study of Nivolumab in Non-Small Cell Lung Cancer",
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Bristol-Myers Squibb"},
                },
                "statusModule": {
                    "phase": "Phase 3",
                },
                "descriptionModule": {
                    "briefSummary": "This study evaluates nivolumab in NSCLC patients.",
                },
                "contactsLocationsModule": {
                    "locations": [{"country": "United States"}],
                },
            },
        },
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT04201277",
                    "briefTitle": "A Study of Nivolumab in Melanoma",
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Bristol-Myers Squibb"},
                },
                "statusModule": {
                    "phase": "Phase 2",
                },
                "descriptionModule": {
                    "briefSummary": "This study evaluates nivolumab in melanoma patients.",
                },
                "contactsLocationsModule": {
                    "locations": [{"country": "United States"}],
                },
            },
        },
    ],
    "nextPageToken": None,
}


@pytest.mark.asyncio
async def test_clinicaltrials_ingestion_creates_documents_and_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ClinicalTrials.gov sync creates source_documents and events."""
    # Create molecule
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab",
        "reference_brand": "Opdivo",
        "manufacturer": "Bristol-Myers Squibb",
        "search_terms": ["nivolumab"],
        "indications": {"NSCLC": {"priority": "HIGH"}, "Melanoma": {"priority": "HIGH"}},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_CLINICALTRIALS_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    # Verify source documents created
    docs_result = await db_session.execute(
        select(SourceDocument).where(SourceDocument.molecule_id == molecule["id"])
    )
    docs = list(docs_result.scalars().all())
    assert len(docs) == 2
    assert {d.external_id for d in docs} == {"NCT04201276", "NCT04201277"}

    # Verify events created
    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    events = list(events_result.scalars().all())
    assert len(events) == 2

    # Verify event details
    event_by_nct = {e.source_document.external_id: e for e in events}
    assert "NCT04201276" in event_by_nct
    assert event_by_nct["NCT04201276"].event_type == "clinical_trial"
    assert event_by_nct["NCT04201276"].development_stage == "phase_3"
    assert event_by_nct["NCT04201276"].indication == "NSCLC"


@pytest.mark.asyncio
async def test_clinicaltrials_verification_status_and_confidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Events from ClinicalTrials.gov are verified with confidence > 0.95."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_verify",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT99999999",
                            "briefTitle": "Test Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Test Sponsor"},
                        },
                        "statusModule": {"phase": "Phase 1"},
                        "descriptionModule": {"briefSummary": "Summary"},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await client.post(f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}")

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    assert event.verification_status == "verified"
    assert float(event.verification_confidence) > 0.95
    assert event.verified_sources_count >= 1


@pytest.mark.asyncio
async def test_clinicaltrials_deduplication_by_external_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Duplicate studies by external_id are not ingested twice."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_dedup",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT00000001",
                            "briefTitle": "Original Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Sponsor"},
                        },
                        "statusModule": {"phase": "Phase 1"},
                        "descriptionModule": {"briefSummary": "Original"},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # First ingestion
        await client.post(f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}")

    # Second ingestion with same NCT ID
    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT00000001",
                            "briefTitle": "Duplicate Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Sponsor"},
                        },
                        "statusModule": {"phase": "Phase 2"},
                        "descriptionModule": {"briefSummary": "Duplicate"},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await client.post(f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}")

    docs_result = await db_session.execute(
        select(SourceDocument).where(SourceDocument.molecule_id == molecule["id"])
    )
    docs = list(docs_result.scalars().all())
    assert len(docs) == 1

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    events = list(events_result.scalars().all())
    assert len(events) == 1


@pytest.mark.asyncio
async def test_clinicaltrials_provenance_records_created(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Data provenance records are created for every extracted field."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_prov",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT11111111",
                            "briefTitle": "Provenance Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Provenance Sponsor"},
                        },
                        "statusModule": {"phase": "Phase 3"},
                        "descriptionModule": {"briefSummary": "Provenance test"},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await client.post(f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}")

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    prov_result = await db_session.execute(
        select(DataProvenance).where(DataProvenance.event_id == event.id)
    )
    provenance = list(prov_result.scalars().all())

    field_names = {p.field_name for p in provenance}
    assert "nctId" in field_names
    assert "title" in field_names
    assert "sponsor" in field_names

    for p in provenance:
        assert p.extraction_method is not None
        assert p.raw_value is not None

    # Verify competitor_id provenance record exists
    competitor_prov = [p for p in provenance if p.field_name == "competitor_id"]
    assert len(competitor_prov) == 1
    assert competitor_prov[0].extraction_method.startswith("sponsor_mapping")
    assert float(competitor_prov[0].confidence) >= 0.0


@pytest.mark.asyncio
async def test_scoring_engine_reproducibility() -> None:
    """Same inputs always produce same threat_score and traffic_light."""
    engine = ScoringEngine()

    mock_event = MagicMock()
    mock_event.development_stage = "phase_3"
    mock_event.competitor = MagicMock()
    mock_event.competitor.tier = 1
    mock_event.country = "United States"
    mock_event.indication_priority = "HIGH"
    mock_event.verification_status = "verified"
    mock_event.verified_sources_count = 2
    mock_event.event_date = None

    result1 = engine.score(mock_event)
    result2 = engine.score(mock_event)
    result3 = engine.score(mock_event)

    assert result1["threat_score"] == result2["threat_score"] == result3["threat_score"]
    assert result1["traffic_light"] == result2["traffic_light"] == result3["traffic_light"]
    assert result1["breakdown"] == result2["breakdown"] == result3["breakdown"]


@pytest.mark.asyncio
async def test_press_release_ingestion_and_deduplication(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Press release ingestion works and deduplicates by content hash."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_pr",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    text = "Amgen announces positive Phase 3 results for ABP 206 in NSCLC."
    source_url = "https://amgen.com/news/2025/abp206"

    # First ingestion
    resp1 = await client.post(
        f"/api/v1/jobs/ingest/press-release?text={text}&source_url={source_url}&molecule_id={molecule['id']}"
    )
    assert resp1.status_code == 200

    # Second ingestion with same text (same content hash)
    resp2 = await client.post(
        f"/api/v1/jobs/ingest/press-release?text={text}&source_url={source_url}&molecule_id={molecule['id']}"
    )
    assert resp2.status_code == 200

    docs_result = await db_session.execute(
        select(SourceDocument).where(SourceDocument.molecule_id == molecule["id"])
    )
    docs = list(docs_result.scalars().all())
    # Only one source document due to content_hash deduplication
    assert len(docs) == 1

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    events = list(events_result.scalars().all())
    assert len(events) == 1

    # Verify press release events have proper scoring
    for event in events:
        assert event.threat_score is not None
        assert event.traffic_light in ("Green", "Amber", "Red")
        assert event.score_breakdown is not None



@pytest.mark.asyncio
async def test_clinicaltrials_sponsor_filter_excludes_non_competitors(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Trials from non-canonical sponsors are filtered out and logged."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_filter",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": ["Amgen", "Zydus"],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    mixed_response = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT00000010",
                        "briefTitle": "Amgen Trial",
                    },
                    "sponsorCollaboratorsModule": {
                        "leadSponsor": {"name": "Amgen Inc."},
                    },
                    "statusModule": {"phase": "Phase 3"},
                    "descriptionModule": {"briefSummary": "Amgen study."},
                },
            },
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT00000011",
                        "briefTitle": "Pfizer Trial",
                    },
                    "sponsorCollaboratorsModule": {
                        "leadSponsor": {"name": "Pfizer"},
                    },
                    "statusModule": {"phase": "Phase 2"},
                    "descriptionModule": {"briefSummary": "Pfizer study."},
                },
            },
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT00000012",
                        "briefTitle": "Zydus Trial",
                    },
                    "sponsorCollaboratorsModule": {
                        "leadSponsor": {"name": "Zydus Lifesciences"},
                    },
                    "statusModule": {"phase": "Phase 1"},
                    "descriptionModule": {"briefSummary": "Zydus study."},
                },
            },
        ],
        "nextPageToken": None,
    }

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = mixed_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    docs_result = await db_session.execute(
        select(SourceDocument).where(SourceDocument.molecule_id == molecule["id"])
    )
    docs = list(docs_result.scalars().all())
    # Only Amgen and Zydus trials should be ingested; Pfizer filtered out
    assert len(docs) == 2
    external_ids = {d.external_id for d in docs}
    assert "NCT00000010" in external_ids
    assert "NCT00000012" in external_ids
    assert "NCT00000011" not in external_ids


@pytest.mark.asyncio
async def test_clinicaltrials_uses_search_terms_with_or_syntax(
    client: AsyncClient, db_session: AsyncSession  # noqa: ARG001
) -> None:
    """ClinicalTrials sync uses query.term with OR-joined search_terms."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_terms",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["ABP 206", "HLX18"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )

        # Verify the query.term parameter contains OR-joined search terms
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params is not None
        assert "query.term" in params
        assert "ABP 206 OR HLX18" in params["query.term"]


@pytest.mark.asyncio
async def test_clinicaltrials_ingestion_maps_known_sponsor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Known sponsors like 'Amgen' map to real competitor_id via SponsorMappingService."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_amgen",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    # Create a canonical competitor for Amgen in the database
    competitor_resp = await client.post("/api/v1/competitors", json={
        "molecule_id": molecule["id"],
        "canonical_name": "Amgen",
        "tier": 1,
        "asset_code": "ABP 206",
        "development_stage": "phase_3",
        "status": "active",
        "primary_markets": [],
    })
    assert competitor_resp.status_code == 201

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT05907122",
                            "briefTitle": "Study of ABP 206 in NSCLC",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Amgen", "class": "INDUSTRY"},
                        },
                        "statusModule": {"phase": "Phase 3"},
                        "descriptionModule": {"briefSummary": "ABP 206 biosimilar study."},
                        "contactsLocationsModule": {
                            "locations": [{"country": "United States"}],
                        },
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    # Query events joined to competitors
    stmt = (
        select(Event)
        .join(Competitor, Event.competitor_id == Competitor.id)
        .where(Competitor.canonical_name == "Amgen")
    )
    events_result = await db_session.execute(stmt)
    events = list(events_result.scalars().all())
    assert len(events) > 0
    assert events[0].verification_status in ("verified", "pending")


@pytest.mark.asyncio
async def test_clinicaltrials_ingestion_creates_provenance_for_competitor_mapping(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ competitor_id mapping creates a data_provenance record. """
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_prov_map",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    await client.post("/api/v1/competitors", json={
        "molecule_id": molecule["id"],
        "canonical_name": "Amgen",
        "tier": 1,
        "asset_code": "ABP 206",
        "development_stage": "phase_3",
        "status": "active",
        "primary_markets": [],
    })

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT22222222",
                            "briefTitle": "Provenance Mapping Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Amgen", "class": "INDUSTRY"},
                        },
                        "statusModule": {"phase": "Phase 3"},
                        "descriptionModule": {"briefSummary": "Test summary."},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    prov_result = await db_session.execute(
        select(DataProvenance).where(
            DataProvenance.event_id == event.id,
            DataProvenance.field_name == "competitor_id",
        )
    )
    prov = prov_result.scalar_one_or_none()
    assert prov is not None
    assert prov.extraction_method.startswith("sponsor_mapping")
    assert float(prov.confidence) > 0


@pytest.mark.asyncio
async def test_clinicaltrials_blocked_sponsors_not_created(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Blocked sponsors (e.g., Mayo Clinic) do not create events."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_blocked",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT33333333",
                            "briefTitle": "Mayo Clinic Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Mayo Clinic", "class": "OTHER"},
                        },
                        "statusModule": {"phase": "Phase 2"},
                        "descriptionModule": {"briefSummary": "Academic study."},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    events = list(events_result.scalars().all())
    assert len(events) == 0


@pytest.mark.asyncio
async def test_clinicaltrials_unmatched_industry_flags_for_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unmatched INDUSTRY sponsors create events with competitor_id=NULL."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_unmatched",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT44444444",
                            "briefTitle": "Unknown Sponsor Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Unknown Pharma XYZ123", "class": "INDUSTRY"},
                        },
                        "statusModule": {"phase": "Phase 1"},
                        "descriptionModule": {"briefSummary": "Unknown sponsor study."},
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    events_result = await db_session.execute(
        select(Event).where(
            Event.molecule_id == molecule["id"],
            Event.competitor_id.is_(None),
        )
    )
    events = list(events_result.scalars().all())
    assert len(events) == 1
    assert events[0].review_status == "flagged"


@pytest.mark.asyncio
async def test_end_to_end_pipeline_creates_scored_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Events with mapped competitors receive threat scores and traffic lights."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_scored",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    await client.post("/api/v1/competitors", json={
        "molecule_id": molecule["id"],
        "canonical_name": "Amgen",
        "tier": 1,
        "asset_code": "ABP 206",
        "development_stage": "phase_3",
        "status": "active",
        "primary_markets": [],
    })

    with patch("app.services.ingestion.clinicaltrials.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT55555555",
                            "briefTitle": "Scored Event Trial",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Amgen", "class": "INDUSTRY"},
                        },
                        "statusModule": {"phase": "Phase 3"},
                        "descriptionModule": {"briefSummary": "Scoring test."},
                        "contactsLocationsModule": {
                            "locations": [{"country": "United States"}],
                        },
                    },
                },
            ],
            "nextPageToken": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = await client.post(
            f"/api/v1/jobs/ingest/clinicaltrials?molecule_id={molecule['id']}"
        )
        assert resp.status_code == 200

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    assert event.competitor_id is not None
    assert event.threat_score is not None
    assert 0 <= event.threat_score <= 100
    assert event.traffic_light in ("Green", "Amber", "Red")
    assert event.score_breakdown is not None
