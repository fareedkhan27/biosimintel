"""Idempotent seed script for patent cliff data across all molecules."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from typing import Any

from sqlalchemy import select

sys.path.insert(0, "/Users/fareedkhan/Dev/Biosim")

from app.db.session import AsyncSessionLocal
from app.models.molecule import Molecule
from app.models.patent_cliff import PatentCliff

NIVOLUMAB_PATENTS: list[dict[str, Any]] = [
    {"indication": "Melanoma", "patent_type": "composition", "patent_number": "US9073996", "expiry_date": date(2028, 3, 25), "territory": "US"},
    {"indication": "NSCLC", "patent_type": "method_of_use", "patent_number": "US9447062", "expiry_date": date(2028, 3, 25), "territory": "US"},
    {"indication": "RCC", "patent_type": "method_of_use", "patent_number": "US10039717", "expiry_date": date(2028, 3, 25), "territory": "US"},
    {"indication": "Hepatocellular Carcinoma (HCC)", "patent_type": "method_of_use", "patent_number": "US10548872", "expiry_date": date(2030, 6, 15), "territory": "US"},
    {"indication": "ESCC", "patent_type": "method_of_use", "patent_number": "US11202758", "expiry_date": date(2032, 1, 10), "territory": "US"},
    {"indication": "SCCHN", "patent_type": "method_of_use", "patent_number": "US10898333", "expiry_date": date(2029, 8, 22), "territory": "US"},
]

ADALIMUMAB_PATENTS: list[dict[str, Any]] = [
    {"indication": "Rheumatoid Arthritis", "patent_type": "composition", "patent_number": "US6090382", "expiry_date": date(2023, 12, 31), "territory": "US"},
    {"indication": "Psoriasis", "patent_type": "method_of_use", "patent_number": "US8889173", "expiry_date": date(2027, 8, 15), "territory": "US"},
    {"indication": "Crohn's Disease", "patent_type": "method_of_use", "patent_number": "US8900575", "expiry_date": date(2029, 3, 20), "territory": "US"},
]

TRASTUZUMAB_PATENTS: list[dict[str, Any]] = [
    {"indication": "HER2+ Breast Cancer", "patent_type": "composition", "patent_number": "US5821337", "expiry_date": date(2019, 6, 30), "territory": "US"},
    {"indication": "HER2+ Gastric Cancer", "patent_type": "method_of_use", "patent_number": "US7910568", "expiry_date": date(2029, 9, 15), "territory": "US"},
]

BEVACIZUMAB_PATENTS: list[dict[str, Any]] = [
    {"indication": "Colorectal Cancer", "patent_type": "composition", "patent_number": "US6884879", "expiry_date": date(2019, 7, 31), "territory": "US"},
    {"indication": "NSCLC", "patent_type": "method_of_use", "patent_number": "US8569303", "expiry_date": date(2025, 12, 15), "territory": "US"},
]


async def _seed_for_molecule(
    molecule_name: str,
    patents: list[dict[str, Any]],
) -> int:
    """Seed patent cliffs for a single molecule. Returns number inserted."""
    async with AsyncSessionLocal() as db:
        molecule_result = await db.execute(
            select(Molecule).where(Molecule.molecule_name.ilike(molecule_name))
        )
        molecule = molecule_result.scalar_one_or_none()
        if molecule is None:
            print(f"Molecule '{molecule_name}' not found. Skipping seed.")
            return 0

        existing_result = await db.execute(
            select(PatentCliff).where(PatentCliff.molecule_id == molecule.id)
        )
        if existing_result.scalars().first():
            print(f"Patent cliffs already exist for {molecule.molecule_name}. Skipping.")
            return 0

        for patent in patents:
            db.add(
                PatentCliff(
                    molecule_id=molecule.id,
                    indication=patent["indication"],
                    patent_type=patent["patent_type"],
                    patent_number=patent["patent_number"],
                    expiry_date=patent["expiry_date"],
                    territory=patent["territory"],
                )
            )
        await db.commit()
        print(f"Seeded {len(patents)} patent cliffs for {molecule.molecule_name}.")
        return len(patents)


async def seed_patent_cliffs() -> None:
    total = 0
    total += await _seed_for_molecule("nivolumab", NIVOLUMAB_PATENTS)
    total += await _seed_for_molecule("adalimumab", ADALIMUMAB_PATENTS)
    total += await _seed_for_molecule("trastuzumab", TRASTUZUMAB_PATENTS)
    total += await _seed_for_molecule("bevacizumab", BEVACIZUMAB_PATENTS)
    print(f"\nPatent cliff seeding complete. {total} total patent(s) inserted.")


if __name__ == "__main__":
    asyncio.run(seed_patent_cliffs())
