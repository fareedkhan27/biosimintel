from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.competitor_service import CompetitorService
from app.services.dashboard_service import DashboardService
from app.services.event_service import EventService
from app.services.review_service import ReviewService


@pytest.mark.asyncio
async def test_competitor_service() -> None:
    svc = CompetitorService()
    result = await svc.get_competitor("test-id", AsyncMock())
    assert result == {}


@pytest.mark.asyncio
async def test_dashboard_service() -> None:
    svc = DashboardService()
    result = await svc.get_dashboard("test-id", AsyncMock())
    assert result == {}


@pytest.mark.asyncio
async def test_event_service() -> None:
    svc = EventService()
    result = await svc.get_event("test-id", AsyncMock())
    assert result == {}


@pytest.mark.asyncio
async def test_review_service() -> None:
    svc = ReviewService()
    result = await svc.get_review("test-id", AsyncMock())
    assert result == {}
