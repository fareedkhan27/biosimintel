from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.event import Event
from app.models.geo import CompetitorCapability, Country, Region
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.models.source_document import SourceDocument
from app.services.threat_service import GeoThreatScorer

logger = get_logger(__name__)

EVENT_TYPE_TO_SIGNAL_TYPE: dict[str, SignalType] = {
    "clinical_trial": SignalType.TRIAL_UPDATE,
    "regulatory_milestone": SignalType.APPROVAL,
    "patent_filing": SignalType.PATENT,
    "sec_filing": SignalType.SEC_FILING,
    "press_release": SignalType.PRESS,
    "pricing_update": SignalType.PRICING,
    "combo_announcement": SignalType.COMBO,
}

SIGNAL_TYPE_TO_DEPARTMENTS: dict[SignalType, list[str]] = {
    SignalType.TRIAL_UPDATE: ["commercial", "medical"],
    SignalType.APPROVAL: ["regulatory", "market_access", "commercial"],
    SignalType.PATENT: ["market_access", "finance"],
    SignalType.SEC_FILING: ["finance", "commercial"],
    SignalType.PRESS: ["commercial", "regulatory"],
    SignalType.PRICING: ["market_access", "finance"],
    SignalType.COMBO: ["medical", "commercial"],
}


class SignalIntelligenceService:
    """Ingest events and automatically geo-tag them with relevance scores."""

    def __init__(self) -> None:
        self._score_cache: dict[tuple[UUID | None, str], int] = {}

    async def ingest_and_tag_event(self, event_id: UUID) -> GeoSignal:
        async with AsyncSessionLocal() as db:
            # 1. Load event
            result = await db.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            if event is None:
                raise ValueError(f"Event not found: {event_id}")

            # 2. Determine signal_type
            event_type = cast(str | None, event.event_type)
            signal_type = EVENT_TYPE_TO_SIGNAL_TYPE.get(
                event_type or "", SignalType.PRESS
            )

            # 3. Determine affected countries
            affected_countries: list[Country] = []
            competitor_id = cast(UUID | None, event.competitor_id)
            event_summary = cast(str | None, event.summary)
            event_evidence = cast(str | None, event.evidence_excerpt)
            text_to_search = f" {event_summary or ''} {event_evidence or ''} ".lower()

            if competitor_id is not None:
                # Regions where competitor has capability.confidence_score > 20
                cap_result = await db.execute(
                    select(CompetitorCapability).where(
                        CompetitorCapability.competitor_id == competitor_id,
                        CompetitorCapability.confidence_score > 20,
                    )
                )
                capabilities = cap_result.scalars().all()
                region_ids = [cap.region_id for cap in capabilities if cap.region_id]
                if region_ids:
                    country_result = await db.execute(
                        select(Country).where(Country.region_id.in_(region_ids))
                    )
                    affected_countries.extend(country_result.scalars().all())

                # Keyword matching for country names in summary / evidence
                all_countries_result = await db.execute(select(Country))
                all_countries = all_countries_result.scalars().all()
                seen_country_ids = {c.id for c in affected_countries}
                for country in all_countries:
                    country_name = cast(str | None, country.name)
                    if (
                        country_name
                        and f" {country_name.lower()} " in text_to_search
                        and country.id not in seen_country_ids
                    ):
                        affected_countries.append(country)
                        seen_country_ids.add(country.id)

                # If no specific countries found, tag all countries where competitor has any capability
                if not affected_countries:
                    any_cap_result = await db.execute(
                        select(CompetitorCapability).where(
                            CompetitorCapability.competitor_id == competitor_id
                        )
                    )
                    any_caps = any_cap_result.scalars().all()
                    any_region_ids = [cap.region_id for cap in any_caps if cap.region_id]
                    if any_region_ids:
                        country_result = await db.execute(
                            select(Country).where(Country.region_id.in_(any_region_ids))
                        )
                        affected_countries.extend(country_result.scalars().all())
            else:
                # Default: all active countries
                country_result = await db.execute(
                    select(Country).where(Country.is_active.is_(True))
                )
                affected_countries.extend(country_result.scalars().all())

            if not affected_countries:
                # Fallback to all active countries
                country_result = await db.execute(
                    select(Country).where(Country.is_active.is_(True))
                )
                affected_countries.extend(country_result.scalars().all())

            # 4. Calculate relevance scores per affected country
            scorer = GeoThreatScorer()
            max_score = 0
            if competitor_id is not None and affected_countries:
                score_tasks = []
                for country in affected_countries:
                    cache_key = (competitor_id, cast(str, country.code))
                    if cache_key not in self._score_cache:
                        score_tasks.append(
                            (
                                cache_key,
                                scorer.calculate_relevance_score(
                                    competitor_id, cache_key[1]
                                ),
                            )
                        )

                if score_tasks:
                    results = await asyncio.gather(*[task for _, task in score_tasks])
                    for (cache_key, _), score in zip(score_tasks, results, strict=True):
                        self._score_cache[cache_key] = score

                scores = [
                    self._score_cache[(competitor_id, cast(str, country.code))]
                    for country in affected_countries
                ]
                max_score = max(scores) if scores else 0

            # 5. Department tags
            department_tags = SIGNAL_TYPE_TO_DEPARTMENTS.get(
                signal_type, ["commercial"]
            )

            # 6. Determine tier from source document
            tier = 3
            if event.source_document_id:
                source_result = await db.execute(
                    select(SourceDocument).where(
                        SourceDocument.id == event.source_document_id
                    )
                )
                source_doc = source_result.scalar_one_or_none()
                if source_doc and source_doc.source_type:
                    if source_doc.source_type == "clinical_trials_gov":
                        tier = 1
                    elif source_doc.source_type == "sec_edgar":
                        tier = 2

            # 7. Expires_at
            expires_at: datetime | None = None
            if tier == 3:
                expires_at = datetime.now(UTC) + timedelta(days=7)

            # 8. Confidence
            confidence = (
                Confidence.CONFIRMED
                if tier == 1
                else Confidence.PROBABLE
                if tier == 2
                else Confidence.UNCONFIRMED
            )

            # 9. Create GeoSignal
            country_ids_list = [c.id for c in affected_countries] if affected_countries else []

            geo_signal = GeoSignal(
                event_id=event.id,
                competitor_id=competitor_id,
                molecule_id=event.molecule_id,
                country_ids=country_ids_list,
                signal_type=signal_type,
                confidence=confidence,
                relevance_score=max_score,
                department_tags=department_tags,
                operating_model_relevance=OperatingModelRelevance.ALL,
                delta_note=None,
                source_url=None,
                source_type=event_type,
                tier=tier,
                expires_at=expires_at,
            )
            db.add(geo_signal)
            await db.commit()
            await db.refresh(geo_signal)
            logger.info(
                "GeoSignal created",
                signal_id=str(geo_signal.id),
                event_id=str(event_id),
                signal_type=signal_type.value,
                tier=tier,
            )
            return geo_signal

    async def get_daily_delta(
        self, region_code: str, since: datetime
    ) -> list[GeoSignal]:
        async with AsyncSessionLocal() as db:
            region_result = await db.execute(
                select(Region).where(Region.code == region_code.upper())
            )
            region = region_result.scalar_one_or_none()
            if region is None:
                return []

            country_result = await db.execute(
                select(Country.id).where(Country.region_id == region.id)
            )
            region_country_ids = [row[0] for row in country_result.all()]
            if not region_country_ids:
                return []

            result = await db.execute(
                select(GeoSignal)
                .where(GeoSignal.created_at >= since)
                .where(GeoSignal.country_ids.overlap(region_country_ids))
                .order_by(GeoSignal.relevance_score.desc(), GeoSignal.tier.asc())
            )
            return list(result.scalars().all())

    async def get_signals_for_department(
        self, region_code: str, department: str, since: datetime
    ) -> list[GeoSignal]:
        async with AsyncSessionLocal() as db:
            region_result = await db.execute(
                select(Region).where(Region.code == region_code.upper())
            )
            region = region_result.scalar_one_or_none()
            if region is None:
                return []

            country_result = await db.execute(
                select(Country.id).where(Country.region_id == region.id)
            )
            region_country_ids = [row[0] for row in country_result.all()]
            if not region_country_ids:
                return []

            dept_lower = department.lower()
            result = await db.execute(
                select(GeoSignal)
                .where(GeoSignal.created_at >= since)
                .where(GeoSignal.country_ids.overlap(region_country_ids))
                .where(GeoSignal.department_tags.contains([dept_lower]))
                .order_by(GeoSignal.relevance_score.desc(), GeoSignal.tier.asc())
            )
            return list(result.scalars().all())
