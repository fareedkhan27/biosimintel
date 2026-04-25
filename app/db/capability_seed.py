from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.geo import CompetitorCapability, Region, RegionCode

logger = get_logger(__name__)

# Mapping from requirement display name → search patterns (tried in order)
COMPETITOR_MATCHES: dict[str, list[str]] = {
    "Amgen": ["Amgen"],
    "Sandoz": ["Sandoz"],
    "Zydus Lifesciences": ["Zydus"],
    "Shanghai Henlius": ["Henlius", "Shanghai Henlius"],
    "Xbrane / Intas": ["Xbrane", "Intas", "Xbrane / Intas"],
    "Boan Biotech": ["Boan Biotech"],
    "Biocon Biologics": ["Biocon Biologics"],
    "Reliance Life Sciences": ["Reliance Life Sciences"],
    "Enzene Biosciences": ["Enzene"],
    "NeuClone / Serum Institute": ["NeuClone", "Serum Institute"],
    "mAbxience": ["mAbxience"],
    "Mabpharm": ["Mabpharm"],
    "Dr. Reddy's": ["Dr. Reddy's"],
    "Lupin": ["Lupin"],
    "CinnaGen": ["CinnaGen"],
    "Beacon Medicare": ["Beacon Medicare"],
    "Farmazona": ["Farmazona"],
    "Farmacam S.A": ["Farmacam", "Farmacam S.A"],
}

CAPABILITY_SEED_DATA: dict[str, dict[RegionCode, Any]] = {
    "Amgen": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 95,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 90,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 85,
        },
    },
    "Sandoz": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 95,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 90,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": True,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 85,
        },
    },
    "Zydus Lifesciences": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No EMA MAA filed. No EU biosimilar infrastructure. Generic presence ≠ biologics capability.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 15,
            "source_notes": "No ANVISA biosimilar filing. No LATAM clinical trial. Tishtha™ India only.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 15,
            "source_notes": "No confirmed MEA biosimilar filing.",
        },
    },
    "Shanghai Henlius": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 30,
            "source_notes": "China-first strategy. No EU partner announced.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 15,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 15,
        },
    },
    "Xbrane / Intas": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 75,
            "source_notes": "Intas has EU commercial infrastructure via Accord Healthcare.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 60,
            "source_notes": "Intas has commercial presence in LATAM.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 55,
            "source_notes": "Intas has commercial presence in MEA.",
        },
    },
    "Boan Biotech": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
    },
    "Biocon Biologics": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
    },
    "Reliance Life Sciences": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": True,
            "has_local_manufacturing": False,
            "confidence_score": 40,
            "source_notes": "India-focused but has MEA distribution potential.",
        },
    },
    "Enzene Biosciences": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
        },
    },
    "NeuClone / Serum Institute": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
        },
    },
    "mAbxience": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 50,
            "source_notes": "Phase 3 LEON Study (NCT07221734) recruiting. EU-focused Argentinian company. Potential LATAM entry via regional partnerships.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 45,
            "source_notes": "Argentinian origin. No confirmed ANVISA filing yet but regional proximity.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 20,
        },
    },
    "Mabpharm": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "Phase 1 terminated. Program likely ended. Retain for completeness.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "Phase 1 terminated. Program likely ended. Retain for completeness.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "Phase 1 terminated. Program likely ended. Retain for completeness.",
        },
    },
    "Dr. Reddy's": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has denosumab biosimilar with Alvotech. Monitor pipeline.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has denosumab biosimilar with Alvotech. Monitor pipeline.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has denosumab biosimilar with Alvotech. Monitor pipeline.",
        },
    },
    "Lupin": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Major Indian generic player. Monitor.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Major Indian generic player. Monitor.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Major Indian generic player. Monitor.",
        },
    },
    "CinnaGen": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has teriparatide biosimilar (Zandoriah). Monitor.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has teriparatide biosimilar (Zandoriah). Monitor.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 10,
            "source_notes": "No confirmed nivolumab program. Has teriparatide biosimilar (Zandoriah). Monitor.",
        },
    },
    "Beacon Medicare": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "No confirmed nivolumab program. User assumption. Monitor.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "No confirmed nivolumab program. User assumption. Monitor.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "No confirmed nivolumab program. User assumption. Monitor.",
        },
    },
    "Farmazona": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 0,
            "source_notes": "Not relevant. LATAM-only assumption.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "No confirmed nivolumab program. Likely local LATAM distributor. User assumption. Monitor.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 0,
            "source_notes": "Not relevant. LATAM-only assumption.",
        },
    },
    "Farmacam S.A": {
        RegionCode.CEE_EU: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 0,
            "source_notes": "Not relevant. LATAM-only assumption.",
        },
        RegionCode.LATAM: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 5,
            "source_notes": "No confirmed nivolumab program. Likely local LATAM distributor. User assumption. Monitor.",
        },
        RegionCode.MEA: {
            "has_local_regulatory_filing": False,
            "has_local_commercial_infrastructure": False,
            "has_local_manufacturing": False,
            "confidence_score": 0,
            "source_notes": "Not relevant. LATAM-only assumption.",
        },
    },
}


async def _find_competitor(db: AsyncSession, display_name: str) -> Competitor | None:
    """Find competitor by display name using flexible matching."""
    patterns = COMPETITOR_MATCHES.get(display_name, [display_name])

    for pattern in patterns:
        # Exact case-insensitive match
        result = await db.execute(
            select(Competitor)
            .where(func.lower(Competitor.canonical_name) == pattern.lower())
            .limit(1)
        )
        competitor = result.scalar_one_or_none()
        if competitor is not None:
            return competitor

        # Partial case-insensitive match
        result = await db.execute(
            select(Competitor)
            .where(func.lower(Competitor.canonical_name).like(f"%{pattern.lower()}%"))
            .limit(1)
        )
        competitor = result.scalar_one_or_none()
        if competitor is not None:
            return competitor

    logger.warning("Competitor not found, skipping", name=display_name)
    return None


async def seed_capabilities(db: AsyncSession) -> int:
    """Seed competitor capabilities. Returns number of rows inserted/updated."""
    # Build region lookup
    region_result = await db.execute(select(Region))
    region_map: dict[RegionCode, str] = {}
    for region in region_result.scalars().all():
        code: RegionCode = region.code  # type: ignore[assignment]
        region_map[code] = str(region.id)

    upserted = 0
    for display_name, region_data in CAPABILITY_SEED_DATA.items():
        competitor = await _find_competitor(db, display_name)
        if competitor is None:
            continue

        for region_code, fields in region_data.items():
            region_id = region_map.get(region_code)
            if region_id is None:
                logger.warning("Region not found", region_code=region_code.value)
                continue

            # Check for existing row
            existing_result = await db.execute(
                select(CompetitorCapability).where(
                    CompetitorCapability.competitor_id == competitor.id,
                    CompetitorCapability.region_id == region_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing is not None:
                # Update existing
                for key, value in fields.items():
                    setattr(existing, key, value)
                upserted += 1
            else:
                # Insert new
                stmt = (
                    pg_insert(CompetitorCapability)
                    .values(
                        competitor_id=competitor.id,
                        region_id=region_id,
                        **fields,
                    )
                )
                await db.execute(stmt)
                upserted += 1

    await db.commit()
    logger.info("Competitor capabilities seeded", upserted=upserted)
    return upserted


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        await seed_capabilities(db)


if __name__ == "__main__":
    asyncio.run(main())
