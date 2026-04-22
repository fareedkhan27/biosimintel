from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IngestionException, NotFoundException
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.molecule import Molecule
from app.schemas.job import JobTriggerResponse

router = APIRouter()
logger = get_logger(__name__)


async def _get_molecule_or_404(molecule_id: UUID, db: AsyncSession) -> Molecule:
    result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")
    return molecule


@router.post("/ingest/clinicaltrials", response_model=JobTriggerResponse)
async def ingest_clinicaltrials(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Trigger ClinicalTrials.gov sync for molecule."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.ingestion.clinicaltrials import ClinicalTrialsService
    service = ClinicalTrialsService()
    try:
        molecule = await _get_molecule_or_404(molecule_id, db)
        await service.sync(molecule, db)
        await db.commit()
    except Exception as exc:
        logger.error("ClinicalTrials ingestion failed", error=str(exc), molecule_id=str(molecule_id))
        raise IngestionException(f"ClinicalTrials ingestion failed: {exc}") from exc
    return JobTriggerResponse(
        job_type="clinicaltrials",
        status="queued",
        message="ClinicalTrials sync triggered",
        molecule_id=molecule_id,
    )


@router.post("/ingest/ema", response_model=JobTriggerResponse)
async def ingest_ema(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Trigger EMA sync."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.ingestion.ema import EMAService
    service = EMAService()
    try:
        molecule = await _get_molecule_or_404(molecule_id, db)
        await service.sync(molecule, db)
        await db.commit()
    except Exception as exc:
        logger.error("EMA ingestion failed", error=str(exc), molecule_id=str(molecule_id))
        raise IngestionException(f"EMA ingestion failed: {exc}") from exc
    return JobTriggerResponse(
        job_type="ema",
        status="queued",
        message="EMA sync triggered",
        molecule_id=molecule_id,
    )


@router.post("/ingest/sec-edgar", response_model=JobTriggerResponse)
async def ingest_sec_edgar(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Trigger SEC EDGAR sync."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.ingestion.sec_edgar import SECEDGARService
    service = SECEDGARService()
    try:
        molecule = await _get_molecule_or_404(molecule_id, db)
        await service.sync(molecule, db)
        await db.commit()
    except Exception as exc:
        logger.error("SEC EDGAR ingestion failed", error=str(exc), molecule_id=str(molecule_id))
        raise IngestionException(f"SEC EDGAR ingestion failed: {exc}") from exc
    return JobTriggerResponse(
        job_type="sec_edgar",
        status="queued",
        message="SEC EDGAR sync triggered",
        molecule_id=molecule_id,
    )


@router.post("/ingest/fda-purple-book", response_model=JobTriggerResponse)
async def ingest_fda_purple_book(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Trigger FDA Purple Book sync."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.ingestion.fda_purple_book import FDAPurpleBookService
    service = FDAPurpleBookService()
    try:
        molecule = await _get_molecule_or_404(molecule_id, db)
        await service.sync(molecule, db)
        await db.commit()
    except Exception as exc:
        logger.error("FDA Purple Book ingestion failed", error=str(exc), molecule_id=str(molecule_id))
        raise IngestionException(f"FDA Purple Book ingestion failed: {exc}") from exc
    return JobTriggerResponse(
        job_type="fda_purple_book",
        status="queued",
        message="FDA Purple Book sync triggered",
        molecule_id=molecule_id,
    )


@router.post("/ingest/press-release", response_model=JobTriggerResponse)
async def ingest_press_release(
    text: str,
    source_url: str,
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Ingest unstructured text."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.ingestion.press_release import PressReleaseService
    service = PressReleaseService()
    try:
        molecule = await _get_molecule_or_404(molecule_id, db)
        await service.ingest(text, source_url, molecule, db)
        await db.commit()
    except Exception as exc:
        logger.error("Press release ingestion failed", error=str(exc), molecule_id=str(molecule_id))
        raise IngestionException(f"Press release ingestion failed: {exc}") from exc
    return JobTriggerResponse(
        job_type="press_release",
        status="queued",
        message="Press release ingested",
        molecule_id=molecule_id,
    )


@router.post("/recompute-scores", response_model=JobTriggerResponse)
async def recompute_scores(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    """Recalculate all scores for molecule."""
    await _get_molecule_or_404(molecule_id, db)
    from app.services.engine.scoring import ScoringEngine
    engine = ScoringEngine()
    from app.models.event import Event
    events_res = await db.execute(
        select(Event).where(Event.molecule_id == molecule_id)
    )
    events = list(events_res.scalars().all())
    for event in events:
        scored = engine.score(event)
        event.threat_score = scored["threat_score"]
        event.traffic_light = scored["traffic_light"]
        event.score_breakdown = scored["breakdown"]
    await db.commit()
    return JobTriggerResponse(
        job_type="recompute_scores",
        status="completed",
        message=f"Recomputed scores for {len(events)} events",
        molecule_id=molecule_id,
    )
