from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.combo import ComboCapability, CompetitorMoleculeAssignment, MoleculePair
from app.models.competitor import Competitor
from app.models.molecule import Molecule

logger = get_logger(__name__)

COMPETITOR_ASSIGNMENTS: list[dict[str, Any]] = [
    {
        "search_name": "Amgen",
        "nivolumab_asset": "ABP 206",
        "ipilimumab_asset": "ABP 230",
        "combo_capability": ComboCapability.FULL,
        "is_primary_focus": True,
    },
    {
        "search_name": "Sandoz",
        "nivolumab_asset": "JPB898",
        "ipilimumab_asset": "GP2017",
        "combo_capability": ComboCapability.FULL,
        "is_primary_focus": True,
    },
    {
        "search_name": "Henlius",
        "nivolumab_asset": "HLX18",
        "ipilimumab_asset": "HLX13",
        "combo_capability": ComboCapability.FULL,
        "is_primary_focus": True,
    },
    {
        "search_name": "Xbrane",
        "nivolumab_asset": "Xdivane",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": True,
    },
    {
        "search_name": "Zydus",
        "nivolumab_asset": "Tishtha",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": True,
    },
    {
        "search_name": "Boan Biotech",
        "nivolumab_asset": "BA1104",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": True,
    },
    {
        "search_name": "Biocon Biologics",
        "nivolumab_asset": "undisclosed",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": False,
    },
    {
        "search_name": "Reliance Life Sciences",
        "nivolumab_asset": "R-TPR-067",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": True,
    },
    {
        "search_name": "Enzene",
        "nivolumab_asset": "Enzene-NIV",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": True,
    },
    {
        "search_name": "NeuClone",
        "nivolumab_asset": "NeuClone-NIV",
        "ipilimumab_asset": None,
        "combo_capability": ComboCapability.NONE,
        "is_primary_focus": False,
    },
]


async def seed_ipilimumab(db: AsyncSession) -> Molecule | None:
    """Seed ipilimumab molecule if not present."""
    result = await db.execute(
        select(Molecule).where(Molecule.molecule_name == "Ipilimumab")
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        molecule = Molecule(
            molecule_name="Ipilimumab",
            reference_brand="Yervoy",
            inn="ipilimumab",
            manufacturer="Bristol-Myers Squibb",
            mechanism_of_action="CTLA-4 inhibitor",
            therapeutic_area="Oncology",
            status="active",
            is_reference_product=True,
            is_active=True,
        )
        db.add(molecule)
        logger.info("Ipilimumab seeded")
    else:
        molecule = existing
        logger.info("Ipilimumab already exists")

    # Backfill inn on existing molecule records so combo tracking can resolve them
    nivo_result = await db.execute(
        select(Molecule).where(Molecule.molecule_name == "nivolumab")
    )
    nivolumab = nivo_result.scalar_one_or_none()
    if nivolumab is not None and nivolumab.inn is None:
        nivolumab.inn = "nivolumab"  # type: ignore[unreachable]
        logger.info("Backfilled nivolumab inn")

    ipi_result = await db.execute(
        select(Molecule).where(Molecule.molecule_name == "Ipilimumab")
    )
    ipilimumab = ipi_result.scalar_one_or_none()
    if ipilimumab is not None and ipilimumab.inn is None:
        ipilimumab.inn = "ipilimumab"  # type: ignore[unreachable]
        logger.info("Backfilled ipilimumab inn")

    await db.commit()
    if molecule:
        await db.refresh(molecule)
        logger.info("Ipilimumab ready", molecule_id=str(molecule.id))
    return molecule


async def seed_competitor_assignments(db: AsyncSession) -> int:
    """Seed competitor molecule assignments and molecule pair."""
    nivo_result = await db.execute(
        select(Molecule).where(Molecule.inn == "nivolumab")
    )
    nivolumab = nivo_result.scalar_one_or_none()
    if nivolumab is None:
        logger.warning("Nivolumab not found, skipping assignments")
        return 0

    ipi_result = await db.execute(
        select(Molecule).where(Molecule.inn == "ipilimumab")
    )
    ipilimumab = ipi_result.scalar_one_or_none()
    if ipilimumab is None:
        logger.warning("Ipilimumab not found, skipping assignments")
        return 0

    nivolumab_id = nivolumab.id
    ipilimumab_id = ipilimumab.id

    inserted = 0
    for entry in COMPETITOR_ASSIGNMENTS:
        search_name = entry["search_name"]
        comp_result = await db.execute(
            select(Competitor)
            .where(func.lower(Competitor.canonical_name) == search_name.lower())
            .limit(1)
        )
        competitor = comp_result.scalar_one_or_none()
        if competitor is None:
            logger.warning("Competitor not found, skipping", name=search_name)
            continue

        # Nivolumab assignment
        stmt = (
            pg_insert(CompetitorMoleculeAssignment)
            .values(
                competitor_id=competitor.id,
                molecule_id=nivolumab_id,
                asset_name=entry["nivolumab_asset"],
                combo_capability=entry["combo_capability"],
                is_primary_focus=entry["is_primary_focus"],
            )
            .on_conflict_do_nothing(
                index_elements=["competitor_id", "molecule_id"]
            )
        )
        await db.execute(stmt)
        inserted += 1

        # Ipilimumab assignment (if present)
        if entry["ipilimumab_asset"]:
            stmt = (
                pg_insert(CompetitorMoleculeAssignment)
                .values(
                    competitor_id=competitor.id,
                    molecule_id=ipilimumab_id,
                    asset_name=entry["ipilimumab_asset"],
                    combo_capability=entry["combo_capability"],
                    is_primary_focus=entry["is_primary_focus"],
                )
                .on_conflict_do_nothing(
                    index_elements=["competitor_id", "molecule_id"]
                )
            )
            await db.execute(stmt)
            inserted += 1

    # Seed molecule pair
    pair_result = await db.execute(
        select(MoleculePair).where(
            MoleculePair.primary_molecule_id == nivolumab_id,
            MoleculePair.secondary_molecule_id == ipilimumab_id,
        )
    )
    existing_pair = pair_result.scalar_one_or_none()
    if existing_pair is None:
        pair = MoleculePair(
            primary_molecule_id=nivolumab_id,
            secondary_molecule_id=ipilimumab_id,
            combo_name="Opdivo + Yervoy",
            is_active=True,
        )
        db.add(pair)
        logger.info("Molecule pair seeded")
    else:
        logger.info("Molecule pair already exists")

    await db.commit()
    logger.info("Competitor assignments seeded", inserted=inserted)
    return inserted


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        await seed_ipilimumab(db)
        await seed_competitor_assignments(db)


if __name__ == "__main__":
    asyncio.run(main())
