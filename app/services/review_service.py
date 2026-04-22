from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


class ReviewService:
    """Review management service."""

    async def get_review(self, review_id: str, _db: AsyncSession) -> dict[str, Any]:
        logger.info("Review service called", review_id=review_id)
        return {}
