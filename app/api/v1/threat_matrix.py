from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import verify_api_key
from app.services.threat_service import GeoThreatScorer

router = APIRouter()


@router.get("/country/{country_code}")
async def get_country_threat_summary(
    country_code: str,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return threat summary for a specific country."""
    scorer = GeoThreatScorer()
    return await scorer.get_country_threat_summary(country_code)


@router.get("/region/{region_code}")
async def get_region_threat_heatmap(
    region_code: str,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return threat heatmap for a specific region."""
    scorer = GeoThreatScorer()
    return await scorer.get_region_threat_heatmap(region_code)


@router.get("/competitor/{competitor_id}")
async def get_competitor_threat_profile(
    competitor_id: UUID,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return threat profile for a competitor across all countries."""
    scorer = GeoThreatScorer()
    return await scorer.get_competitor_threat_profile(competitor_id)
