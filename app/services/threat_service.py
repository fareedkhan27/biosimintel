from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.combo import ComboCapability, CompetitorMoleculeAssignment
from app.models.competitor import Competitor
from app.models.geo import CompetitorCapability, Country, Region
from app.models.molecule import Molecule

logger = get_logger(__name__)

STAGE_40_KEYWORDS = ("phase 3", "bla", "prep", "approved", "filing", "launched", "phase_3")
STAGE_15_KEYWORDS = ("phase 1", "phase 2", "ind", "phase_1", "phase_2", "phase_1_2")
STAGE_5_KEYWORDS = ("preclinical", "undisclosed", "pipeline", "pre_clinical")


def _score_stage(stage: str | None) -> int:
    if not stage:
        return 5
    lower = stage.lower()
    if any(k in lower for k in STAGE_40_KEYWORDS):
        return 40
    if any(k in lower for k in STAGE_15_KEYWORDS):
        return 15
    if any(k in lower for k in STAGE_5_KEYWORDS):
        return 5
    return 5


def _combo_bonus(capability: ComboCapability | None) -> int:
    if capability == ComboCapability.FULL:
        return 10
    if capability == ComboCapability.PARTIAL:
        return 5
    return 0


def _apply_multiplier(raw_score: float, operating_model: Any) -> float:
    if operating_model and operating_model.value == "OPM":
        return raw_score * 1.2
    if operating_model and operating_model.value == "Passive":
        return raw_score * 0.5
    return raw_score


class GeoThreatScorer:
    """Geo-threat scoring engine for competitor capability analysis."""

    async def _resolve_nivolumab_id(self, db: AsyncSession) -> UUID | None:
        result = await db.execute(select(Molecule).where(Molecule.inn == "nivolumab"))
        nivo = result.scalar_one_or_none()
        return nivo.id if nivo else None  # type: ignore[return-value]

    async def _get_competitor_stage(self, db: AsyncSession, competitor_id: UUID) -> str | None:
        """Return highest development stage from assignments, falling back to competitor."""
        result = await db.execute(
            select(CompetitorMoleculeAssignment).where(
                CompetitorMoleculeAssignment.competitor_id == competitor_id
            )
        )
        assignments = result.scalars().all()

        best = 0
        best_stage: str | None = None
        for assignment in assignments:
            stage = cast(str | None, assignment.development_stage)
            if stage:
                score = _score_stage(stage)
                if score > best:
                    best = score
                    best_stage = stage

        if best == 0:
            comp_result = await db.execute(
                select(Competitor).where(Competitor.id == competitor_id)
            )
            competitor = comp_result.scalar_one_or_none()
            if competitor:
                return cast(str | None, competitor.development_stage)

        return best_stage

    def _calc_relevance_score(
        self,
        country: Country,
        competitor_stage: str | None,
        capability: CompetitorCapability | None,
        combo_capability: ComboCapability | None,
    ) -> int:
        base_score = _score_stage(competitor_stage)

        geo_bonus = 0
        if capability:
            if capability.has_local_commercial_infrastructure:
                geo_bonus += 25
            if capability.has_local_regulatory_filing:
                geo_bonus += 15
            if capability.has_local_manufacturing:
                geo_bonus += 10

        combo = _combo_bonus(combo_capability)

        raw_score = base_score + geo_bonus + combo
        multiplied = _apply_multiplier(float(raw_score), country.operating_model)

        return min(int(multiplied), 100)

    async def calculate_relevance_score(self, competitor_id: UUID, country_code: str) -> int:
        async with AsyncSessionLocal() as db:
            country_result = await db.execute(
                select(Country).where(Country.code == country_code.upper())
            )
            country = country_result.scalar_one_or_none()
            if country is None:
                logger.warning("Country not found", country_code=country_code)
                return 0

            competitor_stage = await self._get_competitor_stage(db, competitor_id)

            capability = None
            if country.region_id:
                cap_result = await db.execute(
                    select(CompetitorCapability).where(
                        CompetitorCapability.competitor_id == competitor_id,
                        CompetitorCapability.region_id == country.region_id,
                    )
                )
                capability = cap_result.scalar_one_or_none()

            combo_capability: ComboCapability | None = None
            nivo_id = await self._resolve_nivolumab_id(db)
            if nivo_id:
                nivo_result = await db.execute(
                    select(CompetitorMoleculeAssignment).where(
                        CompetitorMoleculeAssignment.competitor_id == competitor_id,
                        CompetitorMoleculeAssignment.molecule_id == nivo_id,
                    )
                )
                nivo_assignment = nivo_result.scalar_one_or_none()
                if nivo_assignment:
                    combo_capability = cast(ComboCapability | None, nivo_assignment.combo_capability)

            return self._calc_relevance_score(country, competitor_stage, capability, combo_capability)

    async def get_country_threat_summary(self, country_code: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            country_result = await db.execute(
                select(Country).where(Country.code == country_code.upper())
            )
            country = country_result.scalar_one_or_none()
            if country is None:
                return {
                    "country_code": country_code.upper(),
                    "country_name": "",
                    "operating_model": "",
                    "region": "",
                    "competitors": [],
                }

            region_result = await db.execute(select(Region).where(Region.id == country.region_id))
            region = region_result.scalar_one_or_none()

            nivo_id = await self._resolve_nivolumab_id(db)
            if nivo_id is None:
                return {
                    "country_code": country.code,
                    "country_name": country.name,
                    "operating_model": country.operating_model.value if country.operating_model else "",
                    "region": region.name if region else "",
                    "competitors": [],
                }

            # Fetch all nivolumab assignments with competitors in one query
            assignments_result = await db.execute(
                select(CompetitorMoleculeAssignment, Competitor)
                .join(Competitor, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
                .where(CompetitorMoleculeAssignment.molecule_id == nivo_id)
            )
            rows = assignments_result.all()

            # Fetch capabilities for all competitors in this region
            competitor_ids = [cast(UUID, row[0].competitor_id) for row in rows]
            capabilities: dict[UUID, CompetitorCapability] = {}
            if competitor_ids and country.region_id:
                cap_result = await db.execute(
                    select(CompetitorCapability).where(
                        CompetitorCapability.competitor_id.in_(competitor_ids),
                        CompetitorCapability.region_id == country.region_id,
                    )
                )
                for cap in cap_result.scalars().all():
                    cid = cast(UUID, cap.competitor_id)
                    capabilities[cid] = cap

            competitors = []
            for assignment, competitor in rows:
                stage = cast(str | None, assignment.development_stage) or cast(
                    str | None, competitor.development_stage
                )
                cid = cast(UUID, assignment.competitor_id)
                capability = capabilities.get(cid)
                combo = cast(ComboCapability | None, assignment.combo_capability)
                score = self._calc_relevance_score(country, stage, capability, combo)
                threat_level = "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"

                competitors.append(
                    {
                        "competitor_id": str(cid),
                        "competitor_name": competitor.canonical_name,
                        "asset_name": assignment.asset_name,
                        "development_stage": stage or "",
                        "combo_capability": combo.value if combo else "NONE",
                        "relevance_score": score,
                        "threat_level": threat_level,
                    }
                )

            competitors.sort(key=lambda x: x["relevance_score"], reverse=True)

            return {
                "country_code": country.code,
                "country_name": country.name,
                "operating_model": country.operating_model.value if country.operating_model else "",
                "region": region.name if region else "",
                "competitors": competitors,
            }

    async def get_region_threat_heatmap(self, region_code: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            region_result = await db.execute(
                select(Region).where(Region.code == region_code.upper())
            )
            region = region_result.scalar_one_or_none()
            if region is None:
                return {
                    "region_code": region_code.upper(),
                    "region_name": "",
                    "country_count": 0,
                    "high_threat_count": 0,
                    "medium_threat_count": 0,
                    "low_threat_count": 0,
                    "countries": [],
                }

            countries_result = await db.execute(
                select(Country).where(Country.region_id == region.id)
            )
            countries = list(countries_result.scalars().all())

            nivo_id = await self._resolve_nivolumab_id(db)
            if nivo_id is None:
                return {
                    "region_code": region.code.value if region.code else region_code.upper(),
                    "region_name": region.name,
                    "country_count": len(countries),
                    "high_threat_count": 0,
                    "medium_threat_count": 0,
                    "low_threat_count": 0,
                    "countries": [
                        {
                            "country_code": c.code,
                            "country_name": c.name,
                            "operating_model": c.operating_model.value if c.operating_model else "",
                            "high_threat_competitors": 0,
                            "medium_threat_competitors": 0,
                            "low_threat_competitors": 0,
                        }
                        for c in countries
                    ],
                }

            # Fetch all nivolumab assignments with competitors
            assignments_result = await db.execute(
                select(CompetitorMoleculeAssignment, Competitor)
                .join(Competitor, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
                .where(CompetitorMoleculeAssignment.molecule_id == nivo_id)
            )
            assignment_rows = assignments_result.all()

            competitor_ids = [cast(UUID, row[0].competitor_id) for row in assignment_rows]

            # Fetch all capabilities for this region
            cap_result = await db.execute(
                select(CompetitorCapability).where(
                    CompetitorCapability.competitor_id.in_(competitor_ids),
                    CompetitorCapability.region_id == region.id,
                )
            )
            capabilities: dict[UUID, CompetitorCapability] = {}
            for cap in cap_result.scalars().all():
                cid = cast(UUID, cap.competitor_id)
                capabilities[cid] = cap

            # Build lookup for competitor stage
            competitor_stages: dict[UUID, str | None] = {}
            for assignment, competitor in assignment_rows:
                cid = cast(UUID, assignment.competitor_id)
                stage = cast(str | None, assignment.development_stage) or cast(
                    str | None, competitor.development_stage
                )
                competitor_stages[cid] = stage

            countries_data = []
            high_threat_count = 0
            medium_threat_count = 0
            low_threat_count = 0

            for country in countries:
                high = 0
                medium = 0
                low = 0

                for assignment, _competitor in assignment_rows:
                    cid = cast(UUID, assignment.competitor_id)
                    stage = competitor_stages.get(cid)
                    capability = capabilities.get(cid)
                    combo = cast(ComboCapability | None, assignment.combo_capability)
                    score = self._calc_relevance_score(country, stage, capability, combo)
                    if score >= 75:
                        high += 1
                    elif score >= 50:
                        medium += 1
                    else:
                        low += 1

                high_threat_count += high
                medium_threat_count += medium
                low_threat_count += low

                countries_data.append(
                    {
                        "country_code": country.code,
                        "country_name": country.name,
                        "operating_model": country.operating_model.value if country.operating_model else "",
                        "high_threat_competitors": high,
                        "medium_threat_competitors": medium,
                        "low_threat_competitors": low,
                    }
                )

            return {
                "region_code": region.code.value if region.code else region_code.upper(),
                "region_name": region.name,
                "country_count": len(countries),
                "high_threat_count": high_threat_count,
                "medium_threat_count": medium_threat_count,
                "low_threat_count": low_threat_count,
                "countries": countries_data,
            }

    async def get_competitor_threat_profile(self, competitor_id: UUID) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            comp_result = await db.execute(
                select(Competitor).where(Competitor.id == competitor_id)
            )
            competitor = comp_result.scalar_one_or_none()
            if competitor is None:
                return {
                    "competitor_id": str(competitor_id),
                    "competitor_name": "",
                    "countries": [],
                }

            countries_result = await db.execute(select(Country))
            countries = countries_result.scalars().all()

            competitor_stage = await self._get_competitor_stage(db, competitor_id)

            nivo_id = await self._resolve_nivolumab_id(db)
            combo_capability: ComboCapability | None = None
            if nivo_id:
                nivo_result = await db.execute(
                    select(CompetitorMoleculeAssignment).where(
                        CompetitorMoleculeAssignment.competitor_id == competitor_id,
                        CompetitorMoleculeAssignment.molecule_id == nivo_id,
                    )
                )
                nivo_assignment = nivo_result.scalar_one_or_none()
                if nivo_assignment:
                    combo_capability = cast(ComboCapability | None, nivo_assignment.combo_capability)

            # Fetch capabilities for all regions
            capabilities: dict[UUID, CompetitorCapability] = {}
            cap_result = await db.execute(
                select(CompetitorCapability).where(
                    CompetitorCapability.competitor_id == competitor_id
                )
            )
            for cap in cap_result.scalars().all():
                rid = cast(UUID, cap.region_id)
                capabilities[rid] = cap

            countries_data = []
            for country in countries:
                country_rid = cast(UUID | None, country.region_id)
                capability = capabilities.get(country_rid) if country_rid else None
                score = self._calc_relevance_score(
                    country, competitor_stage, capability, combo_capability
                )
                threat_level = "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
                countries_data.append(
                    {
                        "country_code": country.code,
                        "country_name": country.name,
                        "relevance_score": score,
                        "threat_level": threat_level,
                        "operating_model": country.operating_model.value if country.operating_model else "",
                    }
                )

            countries_data.sort(key=lambda x: x["relevance_score"], reverse=True)

            return {
                "competitor_id": str(competitor_id),
                "competitor_name": competitor.canonical_name,
                "countries": countries_data,
            }
