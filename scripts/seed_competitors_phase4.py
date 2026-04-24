"""Idempotent seed script for Phase 4C competitors with CIK validation."""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/Users/fareedkhan/Dev/Biosim")

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.molecule import Molecule

USER_AGENT = settings.SEC_EDGAR_USER_AGENT

ADALIMUMAB_COMPETITORS: list[dict[str, Any]] = [
    {"name": "Amgen", "cik": "0000318154", "biosimilar_name": "Amjevita", "status": "approved", "territory": "US, EU"},
    {"name": "Boehringer Ingelheim", "cik": None, "biosimilar_name": "Cyltezo", "status": "approved", "territory": "US, EU"},
    {"name": "Samsung Bioepis", "cik": None, "biosimilar_name": "Hadlima", "status": "approved", "territory": "US, EU"},
    {"name": "Sandoz", "cik": "0001992829", "biosimilar_name": "Hyrimoz", "status": "approved", "territory": "US, EU"},
    {"name": "Fresenius Kabi", "cik": None, "biosimilar_name": "Idacio", "status": "approved", "territory": "EU"},
    {"name": "Celltrion", "cik": None, "biosimilar_name": "Yuflyma", "status": "approved", "territory": "EU, UK"},
]

TRASTUZUMAB_COMPETITORS: list[dict[str, Any]] = [
    {"name": "Celltrion", "cik": None, "biosimilar_name": "Herzuma", "status": "approved", "territory": "US, EU"},
    {"name": "Amgen", "cik": "0000318154", "biosimilar_name": "Kanjinti", "status": "approved", "territory": "US, EU"},
    {"name": "Mylan", "cik": "0000067800", "biosimilar_name": "Ogivri", "status": "approved", "territory": "US, EU"},
    {"name": "Samsung Bioepis", "cik": None, "biosimilar_name": "Ontruzant", "status": "approved", "territory": "US, EU"},
    {"name": "Pfizer", "cik": "0000078003", "biosimilar_name": "Trazimera", "status": "approved", "territory": "US, EU"},
    {"name": "Accord Healthcare", "cik": None, "biosimilar_name": "Zercepac", "status": "approved", "territory": "EU"},
]

BEVACIZUMAB_COMPETITORS: list[dict[str, Any]] = [
    {"name": "Amgen", "cik": "0000318154", "biosimilar_name": "Mvasi", "status": "approved", "territory": "US, EU"},
    {"name": "Pfizer", "cik": "0000078003", "biosimilar_name": "Zirabev", "status": "approved", "territory": "US, EU"},
    {"name": "Celltrion", "cik": None, "biosimilar_name": "Vegzelma", "status": "approved", "territory": "US, EU"},
    {"name": "Samsung Bioepis", "cik": None, "biosimilar_name": "Alymsys", "status": "approved", "territory": "EU"},
]


def _territory_to_markets(territory: str) -> list[str]:
    """Convert territory string to primary_markets list."""
    return [t.strip() for t in territory.split(",") if t.strip()]


def _status_to_fields(status: str) -> dict[str, str]:
    """Map simple status to development_stage and status fields."""
    if status == "approved":
        return {"development_stage": "launched", "status": "active"}
    return {"development_stage": "pre_clinical", "status": "active"}


async def _validate_cik(cik: str) -> bool:
    """Fetch SEC submissions to verify CIK is valid and reachable."""
    padded = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("name"))
    except Exception as exc:
        print(f"  CIK {cik} validation failed: {exc}")
        return False


async def seed_competitors_for_molecule(
    db: AsyncSession,
    molecule: Molecule,
    competitors: list[dict[str, Any]],
) -> int:
    """Seed competitors for a single molecule. Returns number inserted."""
    inserted = 0

    for comp in competitors:
        result = await db.execute(
            select(Competitor).where(
                Competitor.molecule_id == molecule.id,
                Competitor.canonical_name == comp["name"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"  Competitor '{comp['name']}' for '{molecule.molecule_name}' already exists. Skipping.")
            continue

        cik = comp.get("cik")
        if cik:
            valid = await _validate_cik(cik)
            if not valid:
                print(f"  WARNING: CIK {cik} for '{comp['name']}' is invalid. Setting cik=None.")
                cik = None

        status_fields = _status_to_fields(comp["status"])
        markets = _territory_to_markets(comp["territory"])

        # Tier assignment: Tier 1 for US+EU, Tier 2 for EU-only or UK-only
        tier = 1 if "US" in markets and "EU" in markets else 2

        competitor = Competitor(
            molecule_id=molecule.id,
            canonical_name=comp["name"],
            tier=tier,
            asset_code=comp["biosimilar_name"],
            development_stage=status_fields["development_stage"],
            status=status_fields["status"],
            primary_markets=markets,
            launch_window="Launched",
            parent_company=comp["name"],
            partnership_status="solo",
            cik=cik,
        )
        db.add(competitor)
        inserted += 1
        print(f"  Seeded competitor '{comp['name']}' (biosimilar: {comp['biosimilar_name']}) for '{molecule.molecule_name}'.")

    await db.commit()
    return inserted


async def seed_competitors_phase4() -> None:
    """Seed all Phase 4C competitors idempotently."""
    async with AsyncSessionLocal() as db:
        molecules_result = await db.execute(
            select(Molecule).where(Molecule.molecule_name.in_(["adalimumab", "trastuzumab", "bevacizumab"]))
        )
        molecules: dict[str, Molecule] = {str(m.molecule_name): m for m in molecules_result.scalars().all()}

        if "adalimumab" in molecules:
            count = await seed_competitors_for_molecule(db, molecules["adalimumab"], ADALIMUMAB_COMPETITORS)
            print(f"Adalimumab: inserted {count} competitor(s).")
        else:
            print("Adalimumab molecule not found. Skipping competitors.")

        if "trastuzumab" in molecules:
            count = await seed_competitors_for_molecule(db, molecules["trastuzumab"], TRASTUZUMAB_COMPETITORS)
            print(f"Trastuzumab: inserted {count} competitor(s).")
        else:
            print("Trastuzumab molecule not found. Skipping competitors.")

        if "bevacizumab" in molecules:
            count = await seed_competitors_for_molecule(db, molecules["bevacizumab"], BEVACIZUMAB_COMPETITORS)
            print(f"Bevacizumab: inserted {count} competitor(s).")
        else:
            print("Bevacizumab molecule not found. Skipping competitors.")

    print("\nPhase 4C competitor seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed_competitors_phase4())
