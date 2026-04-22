from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.seed_data import COMPETITORS, NIVOLUMAB
from app.db.session import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.molecule import Molecule

logger = get_logger(__name__)


async def seed_molecules(db: AsyncSession) -> Molecule:
    """Seed nivolumab molecule if not exists."""
    result = await db.execute(
        select(Molecule).where(Molecule.molecule_name == NIVOLUMAB["molecule_name"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("Molecule already seeded", molecule=existing.molecule_name)
        return existing

    molecule = Molecule(**NIVOLUMAB)
    db.add(molecule)
    await db.commit()
    await db.refresh(molecule)
    logger.info("Molecule seeded", molecule=molecule.molecule_name)
    return molecule


async def seed_competitors(db: AsyncSession, molecule: Molecule) -> None:
    """Seed 12 canonical competitors for nivolumab."""
    for comp_data in COMPETITORS:
        result = await db.execute(
            select(Competitor).where(
                Competitor.molecule_id == molecule.id,
                Competitor.canonical_name == comp_data["canonical_name"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(
                "Competitor already seeded",
                competitor=existing.canonical_name,
            )
            continue

        competitor = Competitor(
            molecule_id=molecule.id,
            **comp_data,
        )
        db.add(competitor)
        logger.info("Competitor seeded", competitor=competitor.canonical_name)

    await db.commit()


async def run_seeds() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        molecule = await seed_molecules(db)
        await seed_competitors(db, molecule)
    logger.info("Seeding complete")


if __name__ == "__main__":
    asyncio.run(run_seeds())
