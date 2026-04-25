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
from app.models.combo import CompetitorMoleculeAssignment
from app.models.competitor import Competitor
from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailPreference,
    EmailRegionFilter,
)
from app.models.event import Event
from app.models.geo import CompetitorCapability, Country, Region
from app.models.molecule import Molecule
from app.models.sec_filing import SecFiling
from app.models.signal import GeoSignal, SignalType
from app.models.source_document import SourceDocument
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


_WATCH_STAGES = {"watch", "preclinical", "pre_clinical", "terminated"}

_EVENT_TYPE_TO_SOURCE_DISPLAY: dict[str, str] = {
    "clinical_trial": "ClinicalTrials.gov",
    "regulatory_milestone": "EMA EPAR",
    "patent_filing": "USPTO PatentsView",
    "sec_filing": "SEC EDGAR",
    "press_release": "Company Press Release",
    "pricing_update": "Industry Intelligence",
    "combo_announcement": "Industry Intelligence",
}

_COUNTRY_FLAGS: dict[str, str] = {
    "AL": "🇦🇱", "DZ": "🇩🇿", "AR": "🇦🇷", "BA": "🇧🇦", "BR": "🇧🇷",
    "BG": "🇧🇬", "CL": "🇨🇱", "HR": "🇭🇷", "CZ": "🇨🇿", "EG": "🇪🇬",
    "HU": "🇭🇺", "IN": "🇮🇳", "JO": "🇯🇴", "KZ": "🇰🇿", "KE": "🇰🇪",
    "KW": "🇰🇼", "LB": "🇱🇧", "LY": "🇱🇾", "MX": "🇲🇽", "ME": "🇲🇪",
    "MA": "🇲🇦", "NG": "🇳🇬", "OM": "🇴🇲", "PK": "🇵🇰", "PE": "🇵🇪",
    "PL": "🇵🇱", "QA": "🇶🇦", "RO": "🇷🇴", "RS": "🇷🇸", "SA": "🇸🇦",
    "ZA": "🇿🇦", "KR": "🇰🇷", "TR": "🇹🇷", "AE": "🇦🇪", "UY": "🇺🇾",
    "VE": "🇻🇪", "VN": "🇻🇳", "ZW": "🇿🇼",
}

_GLOBAL_PROGRAMS: set[str] = {"Amgen", "Sandoz"}
_SEC_PATTERNS: tuple[str, ...] = ("sec.gov", "edgar", "sec_edgar", "sec_filing")


def _is_global_program(competitor_name: str) -> bool:
    return competitor_name in _GLOBAL_PROGRAMS


def _has_meaningful_regional_presence(capability: Any) -> bool:
    if capability is None:
        return False
    return bool(
        capability.confidence_score >= 50
        or capability.has_local_regulatory_filing
        or capability.has_local_commercial_infrastructure
    )


def _is_watch_stage(stage: str | None) -> bool:
    if not stage:
        return False
    return stage.lower() in _WATCH_STAGES


def _derive_rationale(stage: str | None) -> str:
    if not stage:
        return "→ Development status unknown"
    lower = stage.lower()
    if "launched" in lower:
        return "→ Already launched in reference market"
    if "bla" in lower or "filing" in lower or "approved" in lower:
        return "→ Advanced regulatory stage → regional expansion expected"
    if "phase 3" in lower or "phase3" in lower or "phase_3" in lower:
        return "→ Phase 3 ongoing → regional filing expected"
    if "phase 2" in lower or "phase2" in lower or "phase_2" in lower:
        return "→ Phase 2 → exploring regional partnerships"
    if "phase 1" in lower or "phase1" in lower or "phase_1" in lower:
        return "→ Early clinical development"
    if "preclinical" in lower or "pre_clinical" in lower:
        return "→ Preclinical stage"
    return f"→ {stage}"


def _format_signal_source(signal: GeoSignal, event_lookup: dict[UUID, Event]) -> dict[str, Any]:
    """Build provenance metadata for a single signal."""
    event = event_lookup.get(cast(UUID, signal.event_id)) if signal.event_id else None
    source_doc = event.source_document if event else None

    source_url = signal.source_url or (source_doc.url if source_doc else None)
    raw_source_type = signal.source_type or (cast(str | None, event.event_type) if event else None)
    source_type_display = _EVENT_TYPE_TO_SOURCE_DISPLAY.get(str(raw_source_type or ""), raw_source_type or "Industry Intelligence")
    source_document_id = cast(str | None, source_doc.external_id) if source_doc else None
    fetched_at = signal.created_at.strftime("%Y-%m-%d") if signal.created_at else None

    return {
        "source_url": source_url,
        "source_type": source_type_display,
        "source_document_id": source_document_id,
        "fetched_at": fetched_at,
    }


async def _build_competitor_source_links(competitor_id: UUID, db: AsyncSession) -> list[dict[str, Any]]:
    """Query DB for all authoritative sources for a competitor and return ordered list."""
    sources: list[dict[str, Any]] = []

    # 1. ClinicalTrials.gov (highest authority)
    ct_result = await db.execute(
        select(Event, SourceDocument)
        .join(SourceDocument, Event.source_document_id == SourceDocument.id)
        .where(Event.competitor_id == competitor_id)
        .where(SourceDocument.source_type == "clinical_trial")
        .order_by(Event.created_at.desc())
        .limit(1)
    )
    ct_row = ct_result.one_or_none()
    if ct_row:
        _event, sd = ct_row
        nct_id = cast(str | None, sd.external_id)
        sources.append({
            "name": "ClinicalTrials.gov",
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else cast(str | None, sd.url),
            "id": nct_id,
        })

    # 2. SEC EDGAR
    sec_result = await db.execute(
        select(SecFiling)
        .where(SecFiling.competitor_id == competitor_id)
        .order_by(SecFiling.filing_date.desc())
        .limit(1)
    )
    sec_filing = sec_result.scalar_one_or_none()
    if sec_filing:
        cik = cast(str, sec_filing.cik)
        sources.append({
            "name": "SEC EDGAR",
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            "id": cik,
        })

    # 3. EMA EPAR
    ema_result = await db.execute(
        select(Event, SourceDocument)
        .join(SourceDocument, Event.source_document_id == SourceDocument.id)
        .where(Event.competitor_id == competitor_id)
        .where(SourceDocument.source_type == "regulatory_database")
        .where(SourceDocument.source_name == "ema_medicines_json")
        .order_by(Event.created_at.desc())
        .limit(1)
    )
    ema_row = ema_result.one_or_none()
    if ema_row:
        _event, sd = ema_row
        sources.append({
            "name": "EMA EPAR",
            "url": cast(str | None, sd.url),
            "id": cast(str | None, sd.external_id),
        })

    # 4. Press Release
    pr_result = await db.execute(
        select(Event, SourceDocument)
        .join(SourceDocument, Event.source_document_id == SourceDocument.id)
        .where(Event.competitor_id == competitor_id)
        .where(SourceDocument.source_type == "press_release")
        .order_by(Event.created_at.desc())
        .limit(1)
    )
    pr_row = pr_result.one_or_none()
    if pr_row:
        _event, sd = pr_row
        sources.append({
            "name": "Company Press Release",
            "url": cast(str | None, sd.url),
            "id": None,
        })

    if not sources:
        sources.append({
            "name": "Industry Intelligence",
            "url": None,
            "id": None,
        })

    return sources


def _format_source_links(
    sources: list[dict[str, Any]],
    exclude_patterns: tuple[str, ...] | None = None,
    competitor_name: str = "",
) -> list[dict[str, Any]]:
    """Transform internal source format to template-ready label/url dicts, deduped by URL.

    - Excludes sources matching exclude_patterns (e.g., SEC EDGAR for daily pulse).
    - Replaces dead/missing URLs with a monitoring placeholder and logs a warning.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    exclude_patterns = exclude_patterns or ()

    for s in sources:
        name = s.get("name", "")
        url = s.get("url")

        # Exclude SEC / unwanted patterns
        if any(pat in name.lower() or (url and pat in url.lower()) for pat in exclude_patterns):
            continue

        if url:
            if url in seen:
                continue
            seen.add(url)

        label = f"{name} {s.get('id') or ''}".strip()

        if not url or not str(url).startswith("http"):
            logger.warning(
                "Competitor source link has no public URL",
                competitor=competitor_name,
                source_name=name,
            )
            out.append({"label": label, "url": None, "is_dead": True})
        else:
            out.append({"label": label, "url": url, "is_dead": False})

    return out


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
        format: str = "v2",
    ) -> str:
        if format == "legacy":
            return await self._compose_daily_pulse_legacy(preference, since)
        return await self._compose_daily_pulse_v2(preference, since)

    async def _compose_daily_pulse_v2(
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

        async with AsyncSessionLocal() as db:
            # Resolve monitored molecules (nivolumab + ipilimumab)
            mol_result = await db.execute(
                select(Molecule).where(Molecule.inn.in_(["nivolumab", "ipilimumab"]))
            )
            monitored_molecules = list(mol_result.scalars().all())
            monitored_mol_ids = {cast(UUID, m.id) for m in monitored_molecules}

            # Resolve target regions and countries
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

            countries: list[Country] = []
            if target_region_ids:
                countries_result = await db.execute(
                    select(Country).where(Country.region_id.in_(target_region_ids))
                )
                countries = list(countries_result.scalars().all())

            # --- GLOBAL THREATS & WATCH LIST ---
            global_threats: list[dict[str, Any]] = []
            watch_list: list[dict[str, Any]] = []
            if monitored_mol_ids:
                assignments_result = await db.execute(
                    select(CompetitorMoleculeAssignment, Competitor)
                    .join(Competitor, CompetitorMoleculeAssignment.competitor_id == Competitor.id)
                    .where(CompetitorMoleculeAssignment.molecule_id.in_(monitored_mol_ids))
                )
                assignment_rows = assignments_result.all()

                # Build competitor lookup
                competitor_assignments: dict[UUID, tuple[CompetitorMoleculeAssignment, Competitor]] = {}
                for assignment, competitor in assignment_rows:
                    cid = cast(UUID, competitor.id)
                    competitor_assignments[cid] = (assignment, competitor)

                # Load regional capabilities for all relevant competitors
                competitor_ids = list(competitor_assignments.keys())
                capabilities_result = await db.execute(
                    select(CompetitorCapability)
                    .where(CompetitorCapability.competitor_id.in_(competitor_ids))
                    .where(CompetitorCapability.region_id.in_(target_region_ids))
                )
                capabilities: dict[UUID, Any] = {}
                for cap in capabilities_result.scalars().all():
                    cid = cast(UUID, cap.competitor_id)
                    # Keep the highest-confidence capability per competitor
                    if cid not in capabilities or cap.confidence_score > capabilities[cid].confidence_score:
                        capabilities[cid] = cap

                # Check for recent regional signals per competitor
                signal_result = await db.execute(
                    select(GeoSignal)
                    .where(GeoSignal.created_at >= since)
                    .where(GeoSignal.competitor_id.in_(competitor_ids))
                    .where(GeoSignal.region_id.in_(target_region_ids))
                )
                competitors_with_regional_signals: set[UUID] = {
                    cast(UUID, s.competitor_id) for s in signal_result.scalars().all() if s.competitor_id
                }

                # Collect country summaries (reuses existing efficient query pattern)
                country_summaries: list[tuple[Country, dict[str, Any]]] = []
                for country in countries:
                    summary = await self.threat_svc.get_country_threat_summary(cast(str, country.code))
                    country_summaries.append((country, summary))

                # Invert: competitor -> countries and max score
                competitor_countries: dict[UUID, list[tuple[str, int]]] = {}
                for country, summary in country_summaries:
                    for c in summary["competitors"]:
                        score = c["relevance_score"]
                        stage = c["development_stage"] or ""
                        if _is_watch_stage(stage) or score <= 0:
                            continue
                        cid = UUID(c["competitor_id"])
                        if cid not in competitor_countries:
                            competitor_countries[cid] = []
                        competitor_countries[cid].append((cast(str, country.name), score))

                # Pre-load source links for all assignment competitors
                competitor_sources: dict[UUID, list[dict[str, Any]]] = {}
                for cid in competitor_ids:
                    competitor_sources[cid] = await _build_competitor_source_links(cid, db)

                for cid, (assignment, competitor) in competitor_assignments.items():
                    stage = cast(str | None, assignment.development_stage) or cast(
                        str | None, competitor.development_stage
                    )
                    name = cast(str, competitor.canonical_name)
                    is_global = _is_global_program(name)
                    has_presence = _has_meaningful_regional_presence(capabilities.get(cid))
                    has_signals = cid in competitors_with_regional_signals
                    is_in_region = cid in competitor_countries

                    # Include in Global Threats if: global program, meaningful presence, or regional signals
                    include_in_global = is_global or has_presence or has_signals

                    if include_in_global and is_in_region:
                        affected = competitor_countries[cid]
                        max_score = max(score for _name, score in affected)
                        relevance_label = (
                            "HIGH" if max_score >= 75 else "MEDIUM" if max_score >= 50 else "LOW"
                        )
                        sources = competitor_sources.get(cid, [])
                        source_links = _format_source_links(
                            sources,
                            exclude_patterns=_SEC_PATTERNS,
                            competitor_name=name,
                        )

                        global_threats.append({
                            "competitor_name": name,
                            "product_code": assignment.asset_name or competitor.asset_code or "Unknown",
                            "development_stage": stage or "Unknown",
                            "relevance_score": max_score,
                            "relevance_label": relevance_label,
                            "rationale": _derive_rationale(stage),
                            "affected_countries": [name for name, _score in affected],
                            "source_links": source_links,
                            "verified_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                            "competitor_id": str(cid),
                        })
                    elif not _is_watch_stage(stage):
                        # Watch list: competitors active elsewhere but not meaningfully in this region
                        watch_list.append({
                            "name": name,
                            "product_code": assignment.asset_name or competitor.asset_code or "Unknown",
                            "stage": stage or "Unknown",
                        })

                global_threats.sort(key=lambda x: x["relevance_score"], reverse=True)
                watch_list.sort(key=lambda x: x["name"])

            # --- COUNTRY-SPECIFIC ALERTS ---
            all_signals: list[GeoSignal] = []
            seen_signal_ids: set[UUID] = set()
            for region_code in regions_to_query:
                delta = await self.signal_svc.get_daily_delta(region_code, since)
                for signal in delta:
                    sid = cast(UUID, signal.id)
                    if sid not in seen_signal_ids:
                        all_signals.append(signal)
                        seen_signal_ids.add(sid)

            filtered_signals = self._filter_signals(all_signals, preference)

            # Build event lookup for enrichment
            signal_event_ids = [cast(UUID, s.event_id) for s in filtered_signals if s.event_id]
            event_lookup: dict[UUID, Event] = {}
            if signal_event_ids:
                from sqlalchemy.orm import selectinload
                event_result = await db.execute(
                    select(Event)
                    .options(selectinload(Event.source_document), selectinload(Event.competitor))
                    .where(Event.id.in_(signal_event_ids))
                )
                for evt in event_result.scalars().all():
                    event_lookup[cast(UUID, evt.id)] = evt

            signal_meta: dict[UUID, dict[str, Any]] = {}
            for signal in filtered_signals:
                signal_meta[cast(UUID, signal.id)] = _format_signal_source(signal, event_lookup)

            country_alerts: list[dict[str, Any]] = []
            for country in countries:
                country_signals: list[GeoSignal] = []
                for signal in filtered_signals:
                    cids: list[UUID] = cast(list[UUID], signal.country_ids or [])
                    if country.id not in cids:
                        continue

                    # For trial updates, verify the signal is genuinely about this country
                    if signal.signal_type == SignalType.TRIAL_UPDATE:
                        event = event_lookup.get(cast(UUID, signal.event_id)) if signal.event_id else None
                        is_specific = False
                        if event and (
                            (event.country and event.country.lower() == country.name.lower())
                            or (event.summary and country.name.lower() in event.summary.lower())
                            or (event.evidence_excerpt and country.name.lower() in event.evidence_excerpt.lower())
                        ):
                            is_specific = True
                        if not is_specific:
                            continue

                    country_signals.append(signal)

                # Sort by tier (asc) then relevance_score (desc) and cap at 5 per country
                country_signals.sort(key=lambda s: (s.tier, -cast(int, s.relevance_score or 0)))
                country_signals = country_signals[:5]

                enriched_signals: list[dict[str, Any]] = []
                for signal in country_signals:
                    meta = signal_meta.get(cast(UUID, signal.id), {})
                    event = event_lookup.get(cast(UUID, signal.event_id)) if signal.event_id else None
                    competitor_name = None
                    if signal.competitor_id and event and event.competitor:
                        competitor_name = event.competitor.canonical_name

                    title_parts: list[str] = []
                    if competitor_name:
                        title_parts.append(competitor_name)
                    title_parts.append(signal.signal_type.value.replace("_", " ").title())
                    title = " — ".join(title_parts) if title_parts else "Signal Alert"

                    enriched_signals.append({
                        "id": signal.id,
                        "title": title,
                        "tier": signal.tier,
                        "tier_label": f"Tier {signal.tier}",
                        "signal_type": signal.signal_type.value,
                        "signal_type_display": signal.signal_type.value.replace("_", " ").title(),
                        "description": signal.delta_note or (event.summary if event else None) or "No description available.",
                        "source_url": signal.source_url or meta.get("source_url"),
                        "source_type": meta.get("source_type", "Industry Intelligence"),
                        "source_document_id": meta.get("source_document_id"),
                        "competitor_name": competitor_name,
                        "relevance_score": signal.relevance_score,
                        "created_at": signal.created_at.strftime("%Y-%m-%d") if signal.created_at else None,
                    })

                country_alerts.append({
                    "country_name": cast(str, country.name),
                    "country_code": cast(str, country.code),
                    "flag": _COUNTRY_FLAGS.get(cast(str, country.code), "🌍"),
                    "operating_model": cast(str, country.operating_model.value) if country.operating_model else "",
                    "alert_count": len(enriched_signals),
                    "signals": enriched_signals,
                    "has_activity": len(enriched_signals) > 0,
                })

            country_alerts.sort(key=lambda x: (-x["alert_count"], x["country_name"]))

        env = _get_jinja_env()
        template = env.get_template("daily_pulse.html")
        region_name = (
            regions_to_query[0].replace("_", "/")
            if len(regions_to_query) == 1
            else "All"
        )
        return template.render(
            region_name=region_name,
            report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            global_threats=global_threats,
            country_alerts=country_alerts,
            watch_list=watch_list,
            methodology_note=(
                "Intelligence is sourced from ClinicalTrials.gov, EMA EPAR, and company disclosures. "
                "Each signal is geo-tagged to your markets based on competitor capability and regional relevance. "
                "Relevance scores (0-100) reflect development stage x geo-proximity x combo capability."
            ),
            unsubscribe_url="#",
            year=datetime.now(UTC).year,
        )

    async def _compose_daily_pulse_legacy(
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

        # Enrich signals with provenance metadata
        signal_event_ids = [cast(UUID, s.event_id) for s in all_signals if s.event_id]
        event_lookup: dict[UUID, Event] = {}
        if signal_event_ids:
            async with AsyncSessionLocal() as db:
                from sqlalchemy.orm import selectinload
                event_result = await db.execute(
                    select(Event)
                    .options(selectinload(Event.source_document))
                    .where(Event.id.in_(signal_event_ids))
                )
                for evt in event_result.scalars().all():
                    event_lookup[cast(UUID, evt.id)] = evt

        signal_meta: dict[UUID, dict[str, Any]] = {}
        for signal in all_signals:
            signal_meta[cast(UUID, signal.id)] = _format_signal_source(signal, event_lookup)

        # Country threat cards + watch list
        country_threat_cards: list[dict[str, Any]] = []
        watch_list_by_name: dict[str, dict[str, Any]] = {}
        async with AsyncSessionLocal() as db:
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

            if target_region_ids:
                countries_result = await db.execute(
                    select(Country).where(Country.region_id.in_(target_region_ids))
                )
                countries = list(countries_result.scalars().all())

                # Collect summaries first
                country_summaries: list[tuple[Country, dict[str, Any]]] = []
                for country in countries:
                    summary = await self.threat_svc.get_country_threat_summary(cast(str, country.code))
                    country_summaries.append((country, summary))

                # First pass: identify competitors that are active in ANY country
                active_names: set[str] = set()
                active_competitor_ids: set[UUID] = set()
                for _country, summary in country_summaries:
                    for c in summary["competitors"]:
                        score = c["relevance_score"]
                        stage = c["development_stage"] or ""
                        if not _is_watch_stage(stage) and score >= 50:
                            active_names.add(c["competitor_name"])
                            active_competitor_ids.add(UUID(c["competitor_id"]))

                # Pre-load source links for all active competitors
                competitor_sources: dict[UUID, list[dict[str, Any]]] = {}
                for cid in active_competitor_ids:
                    competitor_sources[cid] = await _build_competitor_source_links(cid, db)

                # Second pass: build country cards and watch list
                for country, summary in country_summaries:
                    active_threats: list[dict[str, Any]] = []

                    for c in summary["competitors"]:
                        score = c["relevance_score"]
                        stage = c["development_stage"] or ""
                        name = c["competitor_name"]
                        cid = UUID(c["competitor_id"])

                        if name in active_names and not _is_watch_stage(stage) and score >= 50:
                            sources = competitor_sources.get(cid, [])
                            primary = sources[0] if sources else {"name": "Industry Intelligence", "url": None, "id": None}
                            active_threats.append({
                                "competitor": name,
                                "asset": c["asset_name"] or "Unknown",
                                "stage": stage or "Unknown",
                                "score": score,
                                "threat_level": c["threat_level"],
                                "color": {
                                    "HIGH": "red",
                                    "MEDIUM": "amber",
                                    "LOW": "green",
                                }.get(c["threat_level"], "green"),
                                "rationale": _derive_rationale(stage),
                                "primary_source": primary["name"],
                                "source_url": primary["url"],
                                "sources": sources,
                            })
                        elif name not in active_names and name not in watch_list_by_name:
                            # Competitor is never active anywhere → watch list
                            watch_list_by_name[name] = {
                                "name": name,
                                "asset": c["asset_name"] or "Unknown",
                                "stage": stage or "Unknown",
                                "score": score,
                            }

                    active_threats.sort(key=lambda x: x["score"], reverse=True)
                    top_threats = active_threats[:3]

                    country_threat_cards.append({
                        "flag": "🌍",
                        "name": country.name,
                        "code": country.code,
                        "operating_model": cast(str, country.operating_model.value) if country.operating_model else "",
                        "is_passive": country.operating_model is not None and country.operating_model.value == "Passive",
                        "threats": top_threats,
                        "threat_count": len(top_threats),
                    })

        watch_list = sorted(watch_list_by_name.values(), key=lambda x: x["name"])

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
        template = env.get_template("daily_pulse_legacy.html")
        return template.render(
            report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            tier1_signals=tier1,
            tier2_signals=tier2,
            tier3_signals=tier3,
            signal_meta=signal_meta,
            country_threat_cards=country_threat_cards,
            watch_list=watch_list,
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
