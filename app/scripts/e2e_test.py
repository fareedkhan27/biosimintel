#!/usr/bin/env python3
"""Biosim Geo-Intelligence End-to-End Integration Test.

Run from project root:
    source .venv/bin/activate
    python app/scripts/e2e_test.py

Exit code:
    0 — all checks passed (GO LIVE)
    1 — one or more checks failed (NO-GO)
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.db.session import AsyncSessionLocal
from app.models.combo import CompetitorMoleculeAssignment, MoleculePair
from app.models.competitor import Competitor
from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailPreference,
    EmailRegionFilter,
    EmailRole,
)
from app.models.event import Event
from app.models.geo import CompetitorCapability, Country, Region
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal
from app.models.signal import GeoSignal
from app.services.combo_service import ComboIntelligenceService
from app.services.email_v2_service import EmailV2Service
from app.services.noise_service import NoiseBlockService
from app.services.signal_service import SignalIntelligenceService
from app.services.threat_service import GeoThreatScorer

API_BASE = os.getenv("BIOSIM_API_BASE", "http://localhost:8001/api/v1")
API_KEY = os.getenv("BIOSIM_API_KEY", "dev")

_test_results: list[dict[str, Any]] = []


async def _check(name: str, fn: Any) -> Any:
    try:
        result = await fn()
        _test_results.append({"name": name, "status": "PASS", "detail": str(result) if result else ""})
        return result
    except Exception as exc:
        _test_results.append({"name": name, "status": "FAIL", "detail": str(exc)})
        print(f"  ❌ FAIL: {name} — {exc}")
        traceback.print_exc()
        return None


async def run_database_checks() -> None:
    print("\n📊 DATABASE LAYER")
    async with AsyncSessionLocal() as db:
        async def _regions() -> str:
            count = (await db.execute(select(func.count()).select_from(Region))).scalar()
            assert count == 3, f"Expected 3, got {count}"
            return f"{count} rows"
        await _check("Regions table: 3 rows", _regions)

        async def _countries() -> str:
            count = (await db.execute(select(func.count()).select_from(Country))).scalar()
            assert count == 37, f"Expected 37, got {count}"
            return f"{count} rows"
        await _check("Countries table: 37 rows", _countries)

        async def _molecules() -> str:
            niv = (await db.execute(select(Molecule).where(Molecule.molecule_name.ilike("%nivolumab%")))).scalars().all()
            ipi = (await db.execute(select(Molecule).where(Molecule.molecule_name.ilike("%ipilimumab%")))).scalars().all()
            assert len(niv) >= 1, "nivolumab not found"
            assert len(ipi) >= 1, "ipilimumab not found"
            return f"nivolumab={len(niv)}, ipilimumab={len(ipi)}"
        await _check("Molecules: nivolumab + ipilimumab present", _molecules)

        async def _competitors() -> str:
            count = (await db.execute(select(func.count()).select_from(Competitor))).scalar()
            assert count is not None and count >= 10, f"Expected >= 10, got {count}"
            return f"{count} rows"
        await _check("Competitors table: >= 10 rows", _competitors)

        async def _events() -> str:
            count = (await db.execute(select(func.count()).select_from(Event))).scalar()
            assert count is not None and count >= 1, f"Expected >= 1, got {count}"
            return f"{count} rows"
        await _check("Events table: >= 1 row", _events)

        async def _signals() -> str:
            count = (await db.execute(select(func.count()).select_from(GeoSignal))).scalar()
            assert count is not None and count >= 1, f"Expected >= 1, got {count}"
            return f"{count} rows"
        await _check("GeoSignals table: >= 1 row", _signals)

        async def _prefs() -> str:
            count = (await db.execute(select(func.count()).select_from(EmailPreference))).scalar()
            assert count == 8, f"Expected 8, got {count}"
            return f"{count} rows"
        await _check("EmailPreferences table: 8 rows", _prefs)

        async def _noise() -> str:
            count = (await db.execute(select(func.count()).select_from(NoiseSignal))).scalar()
            assert count is not None and count >= 0
            return f"{count} rows"
        await _check("NoiseSignals table: >= 0 rows", _noise)

        async def _caps() -> str:
            count = (await db.execute(select(func.count()).select_from(CompetitorCapability))).scalar()
            assert count == 30, f"Expected 30, got {count}"
            return f"{count} rows"
        await _check("CompetitorCapabilities table: 30 rows", _caps)

        async def _pairs() -> str:
            count = (await db.execute(select(func.count()).select_from(MoleculePair))).scalar()
            assert count == 1, f"Expected 1, got {count}"
            return f"{count} rows"
        await _check("MoleculePairs table: 1 row", _pairs)

        async def _assigns() -> str:
            count = (await db.execute(select(func.count()).select_from(CompetitorMoleculeAssignment))).scalar()
            assert count is not None and count >= 10, f"Expected >= 10, got {count}"
            return f"{count} rows"
        await _check("CompetitorMoleculeAssignments table: >= 10 rows", _assigns)


async def run_service_checks() -> None:
    print("\n🔧 SERVICE LAYER")

    async def _relevance() -> str:
        svc = GeoThreatScorer()
        async with AsyncSessionLocal() as db:
            comp = (await db.execute(select(Competitor).limit(1))).scalar_one_or_none()
            assert comp is not None
            from typing import cast
            score = await svc.calculate_relevance_score(cast(UUID, comp.id), "BR")
            assert isinstance(score, int) and 0 <= score <= 100, f"Score {score} out of range"
            return f"score={score}"
    await _check("GeoThreatScorer.calculate_relevance_score() returns int 0-100", _relevance)

    async def _combo() -> str:
        svc = ComboIntelligenceService()
        matrix = await svc.get_combo_threat_matrix()
        assert isinstance(matrix, list) and len(matrix) > 0
        high_competitors = [m["competitor"] for m in matrix if m.get("threat_level") == "HIGH"]
        assert any(c in high_competitors for c in ("Amgen", "Sandoz", "Henlius"))
        return f"HIGH competitors: {high_competitors}"
    await _check("ComboIntelligenceService.get_combo_threat_matrix() returns HIGH for Amgen/Sandoz/Henlius", _combo)

    async def _delta() -> str:
        svc = SignalIntelligenceService()
        since = datetime.now(UTC) - timedelta(days=7)
        results: list[str] = []
        for region in ("CEE_EU", "LATAM", "MEA"):
            delta = await svc.get_daily_delta(region, since)
            assert isinstance(delta, list)
            results.append(f"{region}={len(delta)}")
        return ", ".join(results)
    await _check("SignalIntelligenceService.get_daily_delta() returns list for each region", _delta)

    async def _noise_digest() -> str:
        svc = NoiseBlockService()
        since = datetime.now(UTC) - timedelta(days=7)
        digest = await svc.get_noise_digest("LATAM", since)
        assert isinstance(digest, list)
        return f"{len(digest)} items"
    await _check("NoiseBlockService.get_noise_digest() returns list", _noise_digest)

    async def _daily() -> str:
        svc = EmailV2Service()
        pref = EmailPreference(
            user_email="test@biosimintel.com",
            user_name="Test",
            role=EmailRole.COMMERCIAL,
            region_filter=EmailRegionFilter.LATAM,
            department_filter=EmailDepartmentFilter.ALL,
            operating_model_threshold=EmailOperatingModelThreshold.ALL,
            is_active=True,
        )
        since = datetime.now(UTC) - timedelta(days=1)
        html = await svc.compose_daily_pulse(pref, since)
        assert isinstance(html, str) and "<html" in html.lower()
        return f"{len(html)} chars"
    await _check("EmailV2Service.compose_daily_pulse() returns HTML string", _daily)

    async def _weekly() -> str:
        svc = EmailV2Service()
        pref = EmailPreference(
            user_email="test@biosimintel.com",
            user_name="Test",
            role=EmailRole.COMMERCIAL,
            region_filter=EmailRegionFilter.CEE_EU,
            department_filter=EmailDepartmentFilter.ALL,
            operating_model_threshold=EmailOperatingModelThreshold.ALL,
            is_active=True,
        )
        html = await svc.compose_weekly_strategic(pref)
        assert isinstance(html, str) and "<html" in html.lower()
        return f"{len(html)} chars"
    await _check("EmailV2Service.compose_weekly_strategic() returns HTML string", _weekly)

    async def _gm() -> str:
        svc = EmailV2Service()
        html = await svc.compose_gm_summary()
        assert isinstance(html, str) and "<html" in html.lower()
        return f"{len(html)} chars"
    await _check("EmailV2Service.compose_gm_summary() returns HTML string", _gm)


async def run_api_checks() -> None:
    print("\n🌐 API LAYER")
    headers = {"X-API-Key": API_KEY}
    async with httpx.AsyncClient(base_url=API_BASE, headers=headers, timeout=30.0) as client:

        async def _health() -> str:
            r = await client.get("/health")
            r.raise_for_status()
            data = r.json()
            assert data.get("status") == "ok"
            assert "geo_intelligence" in data.get("dependencies", {})
            return "ok"
        await _check("GET /health — returns ok with geo_intelligence", _health)

        async def _regions() -> str:
            r = await client.get("/regions")
            r.raise_for_status()
            data = r.json()
            regions = data.get("regions", [])
            assert isinstance(regions, list) and len(regions) == 3
            return f"{len(regions)} regions"
        await _check("GET /regions — returns 3 regions", _regions)

        async def _region_detail() -> str:
            r = await client.get("/regions/CEE_EU")
            r.raise_for_status()
            data = r.json()
            countries = data.get("countries", [])
            assert len(countries) == 17, f"Expected 17, got {len(countries)}"
            return f"{len(countries)} countries"
        await _check("GET /regions/CEE_EU — returns 17 countries", _region_detail)

        async def _br() -> str:
            r = await client.get("/countries/BR")
            r.raise_for_status()
            data = r.json()
            assert data.get("code") == "BR"
            assert "threat_summary" in data
            return f"{data.get('name')} — threat_summary present"
        await _check("GET /countries/BR — returns Brazil with threat_summary", _br)

        async def _rs() -> str:
            r = await client.get("/countries/RS")
            r.raise_for_status()
            data = r.json()
            assert data.get("code") == "RS"
            assert "threat_summary" in data
            return f"{data.get('name')} — threat_summary present"
        await _check("GET /countries/RS — returns Serbia with threat_summary", _rs)

        async def _signals() -> str:
            r = await client.get("/signals", params={"region": "LATAM", "limit": 5})
            r.raise_for_status()
            data = r.json()
            assert "items" in data
            return f"{len(data['items'])} items"
        await _check("GET /signals?region=LATAM — returns paginated signals", _signals)

        async def _delta() -> str:
            since = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
            r = await client.get("/signals/delta", params={"region": "CEE_EU", "since": since})
            r.raise_for_status()
            data = r.json()
            signals = data.get("signals", [])
            assert isinstance(signals, list)
            return f"{len(signals)} signals"
        await _check("GET /signals/delta?region=CEE_EU — returns delta", _delta)

        async def _threat_br() -> str:
            r = await client.get("/threat-matrix/country/BR")
            r.raise_for_status()
            data = r.json()
            competitors = data.get("competitors", [])
            zydus = next((t for t in competitors if "zydus" in t.get("competitor_name", "").lower()), None)
            assert zydus is not None, "Zydus not found in BR threats"
            assert zydus.get("threat_level") == "MEDIUM", f"Expected MEDIUM, got {zydus.get('threat_level')}"
            return f"Zydus={zydus.get('threat_level')}"
        await _check("GET /threat-matrix/country/BR — returns Zydus MEDIUM", _threat_br)

        async def _threat_rs() -> str:
            r = await client.get("/threat-matrix/country/RS")
            r.raise_for_status()
            data = r.json()
            competitors = data.get("competitors", [])
            zydus = next((t for t in competitors if "zydus" in t.get("competitor_name", "").lower()), None)
            assert zydus is not None, "Zydus not found in RS threats"
            assert zydus.get("threat_level") == "LOW", f"Expected LOW, got {zydus.get('threat_level')}"
            return f"Zydus={zydus.get('threat_level')}"
        await _check("GET /threat-matrix/country/RS — returns Zydus LOW", _threat_rs)

        async def _threat_region() -> str:
            r = await client.get("/threat-matrix/region/LATAM")
            r.raise_for_status()
            data = r.json()
            assert "countries" in data
            return f"{len(data['countries'])} countries"
        await _check("GET /threat-matrix/region/LATAM — returns heatmap", _threat_region)

        async def _geo_profile() -> str:
            async with AsyncSessionLocal() as db:
                comp = (await db.execute(select(Competitor).where(Competitor.canonical_name.ilike("%amgen%")).limit(1))).scalar_one_or_none()
                assert comp is not None
                comp_id = str(comp.id)
            r = await client.get(f"/competitors/{comp_id}/geo-profile")
            r.raise_for_status()
            data = r.json()
            assert "capabilities" in data
            assert "combo" in data
            return "capabilities + combo present"
        await _check("GET /competitors/{id}/geo-profile — returns capabilities + combo", _geo_profile)

        async def _dash_region() -> str:
            r = await client.get("/dashboard/region/LATAM")
            r.raise_for_status()
            data = r.json()
            assert "top_competitors" in data
            assert "latest_signals" in data
            return "top_competitors + latest_signals present"
        await _check("GET /dashboard/region/LATAM — returns dashboard JSON", _dash_region)

        async def _dash_country() -> str:
            r = await client.get("/dashboard/country/BR")
            r.raise_for_status()
            data = r.json()
            assert "competitor_threats" in data
            return "competitor_threats present"
        await _check("GET /dashboard/country/BR — returns dashboard JSON", _dash_country)

        async def _daily_html() -> str:
            r = await client.get("/intelligence/daily-pulse", params={"region": "LATAM", "department": "commercial"})
            r.raise_for_status()
            assert "<html" in r.text.lower()
            return f"{len(r.text)} chars"
        await _check("GET /intelligence/daily-pulse?region=LATAM — returns HTML", _daily_html)

        async def _weekly_html() -> str:
            r = await client.get("/intelligence/weekly-strategic", params={"region": "CEE_EU"})
            r.raise_for_status()
            assert "<html" in r.text.lower()
            return f"{len(r.text)} chars"
        await _check("GET /intelligence/weekly-strategic?region=CEE_EU — returns HTML", _weekly_html)

        async def _gm_html() -> str:
            r = await client.get("/intelligence/gm-summary")
            r.raise_for_status()
            assert "<html" in r.text.lower()
            return f"{len(r.text)} chars"
        await _check("GET /intelligence/gm-summary — returns HTML", _gm_html)

        async def _post_daily() -> str:
            r = await client.post(
                "/intelligence/daily-pulse",
                json={"region": "MEA", "department": "regulatory", "role": "commercial"},
            )
            r.raise_for_status()
            assert "<html" in r.text.lower()
            return f"{len(r.text)} chars"
        await _check("POST /intelligence/daily-pulse — returns HTML with JSON body", _post_daily)

        async def _noise_expire() -> str:
            r = await client.post("/noise/expire")
            r.raise_for_status()
            data = r.json()
            assert "expired_count" in data and "timestamp" in data
            return f"expired_count={data['expired_count']}"
        await _check("POST /noise/expire — returns JSON with expired_count", _noise_expire)

        async def _noise_digest_api() -> str:
            r = await client.get("/noise/digest", params={"region": "LATAM", "since": "2026-04-18"})
            r.raise_for_status()
            data = r.json()
            assert isinstance(data, list)
            return f"{len(data)} items"
        await _check("GET /noise/digest?region=LATAM — returns noise digest", _noise_digest_api)


async def run_backward_compat_checks() -> None:
    print("\n🔄 BACKWARD COMPATIBILITY")
    headers = {"X-API-Key": API_KEY}
    async with httpx.AsyncClient(base_url=API_BASE, headers=headers, timeout=120.0) as client:

        async def _legacy() -> str:
            r = await client.post(
                "/intelligence/briefing/email",
                json={
                    "molecule_id": "b36cfffb-cbba-4a8e-9742-70920670a02c",
                    "departments": ["market_access"],
                    "since_days": 7,
                },
            )
            r.raise_for_status()
            # Briefing endpoint returns large JSON; just verify it's valid JSON and has expected keys
            data = r.json()
            has_content = "html_content" in data or "body" in data or "subject" in data
            assert has_content, "Legacy briefing missing expected content keys"
            return f"status={r.status_code}, keys={list(data.keys())[:3]}"
        await _check("POST /intelligence/briefing/email — still works (legacy)", _legacy)


async def main() -> int:
    print("=" * 60)
    print("  BIOSIM GEO-INTELLIGENCE E2E TEST SUITE")
    print("=" * 60)

    await run_database_checks()
    await run_service_checks()
    await run_api_checks()
    await run_backward_compat_checks()

    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["status"] == "PASS")
    failed = total - passed

    print("\n" + "=" * 60)
    print("  BIOSIM GEO-INTELLIGENCE E2E TEST RESULTS")
    print("=" * 60)
    for r in _test_results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {icon} {r['name']}")
        if r["detail"]:
            print(f"     → {r['detail']}")
    print("-" * 60)
    if failed == 0:
        print(f"Passed: {passed}/{total}  Failed: {failed}/{total}  Status: ✅ READY FOR DEPLOYMENT")
        return 0
    else:
        print(f"Passed: {passed}/{total}  Failed: {failed}/{total}  Status: FAILED: {failed}/{total} — DO NOT DEPLOY")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
