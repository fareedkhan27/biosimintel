"""Idempotent seed script for Phase 4C molecules: adalimumab, trastuzumab, bevacizumab."""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from sqlalchemy import select

sys.path.insert(0, "/Users/fareedkhan/Dev/Biosim")

from app.db.session import AsyncSessionLocal
from app.models.molecule import Molecule

MOLECULES: list[dict[str, Any]] = [
    {
        "molecule_name": "adalimumab",
        "reference_brand": "Humira",
        "manufacturer": "AbbVie",
        "search_terms": [
            "adalimumab biosimilar",
            "Amjevita",
            "Cyltezo",
            "Hadlima",
            "Hyrimoz",
            "Idacio",
            "Yuflyma",
        ],
        "indications": {
            "Rheumatoid Arthritis": {
                "priority": "HIGH",
                "market_size_usd_b": 8.0,
                "pivotal": True,
            },
            "Psoriasis": {
                "priority": "HIGH",
                "market_size_usd_b": 5.0,
                "pivotal": True,
            },
            "Crohn's Disease": {
                "priority": "MEDIUM",
                "market_size_usd_b": 3.0,
                "pivotal": False,
            },
            "Ulcerative Colitis": {
                "priority": "MEDIUM",
                "market_size_usd_b": 2.5,
                "pivotal": False,
            },
            "Ankylosing Spondylitis": {
                "priority": "MEDIUM",
                "market_size_usd_b": 1.5,
                "pivotal": False,
            },
        },
        "loe_timeline": {
            "US": {
                "date": "2023-01-01",
                "multiplier": 1.5,
                "status": "OPEN",
            },
            "EU": {
                "date": "2018-10-16",
                "multiplier": 1.1,
                "status": "OPEN",
            },
        },
        "competitor_universe": [
            "Amgen",
            "Boehringer Ingelheim",
            "Samsung Bioepis",
            "Sandoz",
            "Fresenius Kabi",
            "Celltrion",
        ],
        "scoring_weights": {},
        "is_active": True,
    },
    {
        "molecule_name": "trastuzumab",
        "reference_brand": "Herceptin",
        "manufacturer": "Roche",
        "search_terms": [
            "trastuzumab biosimilar",
            "Herzuma",
            "Kanjinti",
            "Ogivri",
            "Ontruzant",
            "Trazimera",
            "Zercepac",
        ],
        "indications": {
            "HER2+ Breast Cancer": {
                "priority": "HIGH",
                "market_size_usd_b": 4.5,
                "pivotal": True,
            },
            "HER2+ Gastric Cancer": {
                "priority": "MEDIUM",
                "market_size_usd_b": 1.5,
                "pivotal": False,
            },
        },
        "loe_timeline": {
            "US": {
                "date": "2019-06-30",
                "multiplier": 1.5,
                "status": "OPEN",
            },
            "EU": {
                "date": "2014-07-01",
                "multiplier": 1.1,
                "status": "OPEN",
            },
        },
        "competitor_universe": [
            "Celltrion",
            "Amgen",
            "Mylan",
            "Samsung Bioepis",
            "Pfizer",
            "Accord Healthcare",
        ],
        "scoring_weights": {},
        "is_active": True,
    },
    {
        "molecule_name": "bevacizumab",
        "reference_brand": "Avastin",
        "manufacturer": "Roche",
        "search_terms": [
            "bevacizumab biosimilar",
            "Alymsys",
            "Mvasi",
            "Vegzelma",
            "Zirabev",
        ],
        "indications": {
            "Colorectal Cancer": {
                "priority": "HIGH",
                "market_size_usd_b": 2.5,
                "pivotal": True,
            },
            "NSCLC": {
                "priority": "HIGH",
                "market_size_usd_b": 2.0,
                "pivotal": True,
            },
            "Ovarian Cancer": {
                "priority": "MEDIUM",
                "market_size_usd_b": 1.2,
                "pivotal": False,
            },
            "Glioblastoma": {
                "priority": "MEDIUM",
                "market_size_usd_b": 0.8,
                "pivotal": False,
            },
        },
        "loe_timeline": {
            "US": {
                "date": "2019-07-31",
                "multiplier": 1.5,
                "status": "OPEN",
            },
            "EU": {
                "date": "2018-01-01",
                "multiplier": 1.1,
                "status": "OPEN",
            },
        },
        "competitor_universe": [
            "Amgen",
            "Pfizer",
            "Celltrion",
            "Samsung Bioepis",
        ],
        "scoring_weights": {},
        "is_active": True,
    },
]


async def seed_molecules_phase4() -> dict[str, Molecule]:
    """Seed Phase 4C molecules idempotently. Returns a dict mapping molecule_name to Molecule."""
    seeded: dict[str, Molecule] = {}

    async with AsyncSessionLocal() as db:
        for data in MOLECULES:
            result = await db.execute(
                select(Molecule).where(Molecule.molecule_name == data["molecule_name"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"Molecule '{data['molecule_name']}' already exists. Skipping.")
                seeded[data["molecule_name"]] = existing
                continue

            # New molecules default to silent — user must opt-in
            data.setdefault("briefing_mode", "silent")
            data.setdefault("alert_threshold", 60)
            data.setdefault("is_monitored", True)
            molecule = Molecule(**data)
            db.add(molecule)
            await db.commit()
            await db.refresh(molecule)
            print(f"Seeded molecule '{molecule.molecule_name}' (ID: {molecule.id}).")
            seeded[data["molecule_name"]] = molecule

    return seeded


if __name__ == "__main__":
    molecules = asyncio.run(seed_molecules_phase4())
    print(f"\nPhase 4C molecule seeding complete. {len(molecules)} molecule(s) ready.")
