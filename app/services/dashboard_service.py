from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


class DashboardService:
    """Dashboard data aggregation service."""

    async def get_dashboard(self, molecule_id: str, _db: AsyncSession) -> dict[str, Any]:
        logger.info("Dashboard service called", molecule_id=molecule_id)
        return {}
