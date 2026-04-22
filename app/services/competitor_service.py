from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


class CompetitorService:
    """Competitor management service."""

    async def get_competitor(self, competitor_id: str, _db: AsyncSession) -> dict[str, Any]:
        logger.info("Competitor service called", competitor_id=competitor_id)
        return {}
