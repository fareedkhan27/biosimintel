from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailPreference,
    EmailRegionFilter,
)
from app.models.geo import Country, Region
from app.models.signal import GeoSignal
from app.services.combo_service import ComboIntelligenceService
from app.services.noise_service import NoiseBlockService
from app.services.signal_service import SignalIntelligenceService
from app.services.threat_service import GeoThreatScorer

logger = get_logger(__name__)

_email_template_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
_template_dir = Path(__file__).resolve().parent.parent / "templates"
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(str(_email_template_dir)),
                FileSystemLoader(str(_template_dir)),
            ]),
            autoescape=select_autoescape(["html", "xml"]),
        )
    return _jinja_env


_RELEVANCE_THRESHOLDS: dict[EmailOperatingModelThreshold, int] = {
    EmailOperatingModelThreshold.ALL: 0,
    EmailOperatingModelThreshold.OPM: 60,
    EmailOperatingModelThreshold.LPM: 75,
    EmailOperatingModelThreshold.PASSIVE: 90,
}

_REGION_CODES: dict[EmailRegionFilter, str] = {
    EmailRegionFilter.CEE_EU: "CEE_EU",
    EmailRegionFilter.LATAM: "LATAM",
    EmailRegionFilter.MEA: "MEA",
}


class EmailV2Service:
    """v2 email engine for role-based, region-specific briefings."""

    def __init__(self) -> None:
        self.signal_svc = SignalIntelligenceService()
        self.threat_svc = GeoThreatScorer()
        self.combo_svc = ComboIntelligenceService()

    def _filter_signals(
        self,
        signals: list[GeoSignal],
        preference: EmailPreference,
    ) -> list[GeoSignal]:
        dept = preference.department_filter
        threshold = _RELEVANCE_THRESHOLDS.get(
            cast(EmailOperatingModelThreshold, preference.operating_model_threshold), 0
        )

        filtered: list[GeoSignal] = []
        for signal in signals:
            if signal.relevance_score is not None and signal.relevance_score < threshold:
                continue
            if (
                dept != EmailDepartmentFilter.ALL
                and signal.department_tags
                and dept.value not in signal.department_tags
            ):
                continue
            filtered.append(signal)
        return filtered

    async def compose_daily_pulse(
        self,
        preference: EmailPreference,
        since: datetime,
    ) -> str:
        region_filter = preference.region_filter
        regions_to_query: list[str] = []
        region_filter_val = cast(EmailRegionFilter, region_filter)
        if region_filter_val == EmailRegionFilter.ALL:
            regions_to_query = ["CEE_EU", "LATAM", "MEA"]
        else:
            code = _REGION_CODES.get(region_filter_val)
            if code:
                regions_to_query = [code]

        all_signals: list[GeoSignal] = []
        seen_ids: set[UUID] = set()
        for region_code in regions_to_query:
            delta = await self.signal_svc.get_daily_delta(region_code, since)
            for signal in delta:
                signal_id = cast(UUID, signal.id)
                if signal_id not in seen_ids:
                    all_signals.append(signal)
                    seen_ids.add(signal_id)

        filtered = self._filter_signals(all_signals, preference)

        tier1 = [s for s in filtered if s.tier == 1][:5]
        tier2 = [s for s in filtered if s.tier == 2][:5]
        tier3 = [s for s in filtered if s.tier == 3][:3]

        # Country snapshots
        country_snapshots: list[dict[str, Any]] = []
        if filtered:
            async with AsyncSessionLocal() as db:
                country_ids: set[UUID] = set()
                for signal in filtered:
                    if signal.country_ids:
                        country_ids.update(signal.country_ids)

                if country_ids:
                    result = await db.execute(
                        select(Country).where(Country.id.in_(country_ids))
                    )
                    countries = result.scalars().all()

                    # Filter to user's regions
                    target_region_ids: set[UUID] = set()
                    if region_filter == EmailRegionFilter.ALL:
                        region_res = await db.execute(select(Region))
                        target_region_ids = {cast(UUID, r.id) for r in region_res.scalars().all()}
                    else:
                        region_res = await db.execute(
                            select(Region).where(Region.code == region_filter.value.upper())
                        )
                        region_obj = region_res.scalar_one_or_none()
                        if region_obj:
                            target_region_ids = {cast(UUID, region_obj.id)}

                    for country in countries:
                        if country.region_id in target_region_ids:
                            signal_count = sum(
                                1 for s in filtered
                                if s.country_ids and country.id in s.country_ids
                            )
                            om = cast(str, country.operating_model.value) if country.operating_model else ""
                            country_snapshots.append({
                                "flag": "🌍",
                                "name": country.name,
                                "operating_model": om,
                                "signal_count": signal_count,
                            })

        # Combo threat corner
        combo_threat_level = "LOW"
        combo_threat_detail = "No immediate combo threat detected"
        try:
            matrix = await self.combo_svc.get_combo_threat_matrix()
            if matrix:
                high = [m for m in matrix if m.get("threat_level") == "HIGH"]
                moderate = [m for m in matrix if m.get("threat_level") == "MODERATE"]
                if high:
                    combo_threat_level = "HIGH"
                    combo_threat_detail = f"{high[0]['competitor']} has both molecules in pipeline"
                elif moderate:
                    combo_threat_level = "MODERATE"
                    combo_threat_detail = f"{moderate[0]['competitor']} has partial combo capability"
                else:
                    combo_threat_level = "LOW"
                    combo_threat_detail = "No immediate combo threat detected"
        except Exception as exc:
            logger.warning("Combo threat fetch failed", error=str(exc))

        env = _get_jinja_env()
        template = env.get_template("daily_pulse.html")
        return template.render(
            report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            tier1_signals=tier1,
            tier2_signals=tier2,
            tier3_signals=tier3,
            country_snapshots=country_snapshots,
            combo_threat_level=combo_threat_level,
            combo_threat_detail=combo_threat_detail,
            year=datetime.now(UTC).year,
        )

    async def compose_weekly_strategic(
        self,
        preference: EmailPreference,
    ) -> str:
        since = datetime.now(UTC) - timedelta(days=7)
        region_filter = preference.region_filter
        region_code = _REGION_CODES.get(cast(EmailRegionFilter, region_filter), "CEE_EU")

        async with AsyncSessionLocal() as db:
            region_result = await db.execute(
                select(Region).where(Region.code == region_code.upper())
            )
            region = region_result.scalar_one_or_none()

            signals: list[GeoSignal] = []
            if region:
                country_result = await db.execute(
                    select(Country.id).where(Country.region_id == region.id)
                )
                region_country_ids = [row[0] for row in country_result.all()]
                if region_country_ids:
                    signal_result = await db.execute(
                        select(GeoSignal)
                        .where(GeoSignal.created_at >= since)
                        .where(GeoSignal.country_ids.overlap(region_country_ids))
                        .order_by(GeoSignal.relevance_score.desc())
                    )
                    signals = list(signal_result.scalars().all())

        filtered = self._filter_signals(signals, preference)

        tier1_count = len([s for s in filtered if s.tier == 1])
        tier2_count = len([s for s in filtered if s.tier == 2])
        tier3_count = len([s for s in filtered if s.tier == 3])

        highlight = (
            f"{tier1_count} confirmed, {tier2_count} probable, and {tier3_count} early signals "
            f"recorded in {region_code.replace('_', '/')} this week."
        )

        # Heatmap
        heatmap_data: dict[str, Any] = {}
        try:
            heatmap_data = await self.threat_svc.get_region_threat_heatmap(region_code)
        except Exception as exc:
            logger.warning("Heatmap fetch failed", error=str(exc))

        heatmap_countries = heatmap_data.get("countries", [])

        # Combo assessments
        combo_assessments: list[dict[str, Any]] = []
        try:
            matrix = await self.combo_svc.get_combo_threat_matrix()
            combo_assessments = matrix
        except Exception as exc:
            logger.warning("Combo matrix fetch failed", error=str(exc))

        # Noise digest
        noise_digest: list[dict[str, Any]] = []
        try:
            noise_svc = NoiseBlockService()
            noise_digest = await noise_svc.get_noise_digest(
                region_code, since
            )
        except Exception as exc:
            logger.warning("Noise digest fetch failed", error=str(exc))

        # Recommended actions (generic based on top signals)
        recommended_actions: list[str] = []
        top = [s for s in filtered if s.tier in (1, 2)][:3]
        for signal in top:
            recommended_actions.append(
                f"Review {signal.signal_type.value.replace('_', ' ')} signal "
                f"(relevance {signal.relevance_score})"
            )
        if not recommended_actions:
            recommended_actions.append("Monitor pipeline for new developments this week.")

        env = _get_jinja_env()
        template = env.get_template("weekly_strategic.html")
        return template.render(
            week_range=f"{since.strftime('%Y-%m-%d')} to {datetime.now(UTC).strftime('%Y-%m-%d')}",
            region_name=region_code.replace("_", "/"),
            tier1_count=tier1_count,
            tier2_count=tier2_count,
            tier3_count=tier3_count,
            highlight=highlight,
            heatmap_countries=heatmap_countries,
            timeline_entries=[],
            combo_assessments=combo_assessments,
            recommended_actions=recommended_actions,
            noise_digest=noise_digest,
            year=datetime.now(UTC).year,
        )

    async def compose_gm_summary(self) -> str:
        since = datetime.now(UTC) - timedelta(days=7)

        region_heatmaps: list[dict[str, Any]] = []
        for region_code in ["CEE_EU", "LATAM", "MEA"]:
            try:
                data = await self.threat_svc.get_region_threat_heatmap(region_code)
                region_heatmaps.append({
                    "region_name": data.get("region_name", region_code.replace("_", "/")),
                    "high_threat_count": data.get("high_threat_count", 0),
                    "medium_threat_count": data.get("medium_threat_count", 0),
                    "low_threat_count": data.get("low_threat_count", 0),
                })
            except Exception as exc:
                logger.warning("Region heatmap failed", region=region_code, error=str(exc))
                region_heatmaps.append({
                    "region_name": region_code.replace("_", "/"),
                    "high_threat_count": 0,
                    "medium_threat_count": 0,
                    "low_threat_count": 0,
                })

        # Top 5 signals across all regions
        top_signals: list[GeoSignal] = []
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(GeoSignal)
                    .where(GeoSignal.created_at >= since)
                    .order_by(GeoSignal.relevance_score.desc())
                    .limit(5)
                )
                top_signals = list(result.scalars().all())
        except Exception as exc:
            logger.warning("Top signals fetch failed", error=str(exc))

        # Combo threat summary
        full_combo_competitors: list[str] = []
        try:
            matrix = await self.combo_svc.get_combo_threat_matrix()
            full_combo_competitors = [
                m["competitor"] for m in matrix if m.get("combo_capability") == "FULL"
            ]
        except Exception as exc:
            logger.warning("Combo matrix fetch failed", error=str(exc))

        env = _get_jinja_env()
        template = env.get_template("gm_summary.html")
        return template.render(
            report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            region_heatmaps=region_heatmaps,
            top_signals=top_signals,
            full_combo_competitors=full_combo_competitors,
            row_india="Leading indicator data pending",
            row_china="Leading indicator data pending",
            row_us="Leading indicator data pending",
            year=datetime.now(UTC).year,
        )

    async def get_preference_by_id(
        self, db: AsyncSession, preference_id: UUID
    ) -> EmailPreference | None:
        from sqlalchemy import select
        result = await db.execute(
            select(EmailPreference).where(EmailPreference.id == preference_id)
        )
        return result.scalar_one_or_none()
