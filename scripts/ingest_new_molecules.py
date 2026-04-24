"""Trigger ClinicalTrials.gov ingestion for Phase 4C molecules."""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/Users/fareedkhan/Dev/Biosim")

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.molecule import Molecule
from app.services.ingestion.clinicaltrials import ClinicalTrialsService

logger = get_logger(__name__)

MOLECULE_NAMES = ["adalimumab", "trastuzumab", "bevacizumab"]


async def ingest_molecule(molecule: Molecule, db: AsyncSession) -> int:
    """Trigger ClinicalTrials.gov search for a molecule's search terms."""
    service = ClinicalTrialsService()
    try:
        await service.sync(molecule, db)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Ingestion failed", molecule=molecule.molecule_name, error=str(exc))
        raise
    finally:
        await service.close()

    # Count events created for this molecule to report progress
    from app.models.event import Event
    result = await db.execute(
        select(Event).where(
            Event.molecule_id == molecule.id,
            Event.event_type == "clinical_trial",
        )
    )
    count = len(result.scalars().all())
    return count


async def ingest_new_molecules() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        molecules_result = await db.execute(
            select(Molecule).where(Molecule.molecule_name.in_(MOLECULE_NAMES))
        )
        molecules: dict[str, Molecule] = {str(m.molecule_name): m for m in molecules_result.scalars().all()}

        for name in MOLECULE_NAMES:
            molecule = molecules.get(name)
            if not molecule:
                print(f"Molecule '{name}' not found. Skipping ingestion.")
                continue

            print(f"Starting ClinicalTrials.gov ingestion for '{name}'...")
            try:
                total_trials = await ingest_molecule(molecule, db)
                print(f"  Ingested {total_trials} clinical trials for {name}.")
            except Exception as exc:
                print(f"  WARNING: Ingestion for {name} failed: {exc}")

    print("\nPhase 4C ingestion complete.")


if __name__ == "__main__":
    asyncio.run(ingest_new_molecules())
