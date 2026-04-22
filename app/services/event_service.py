from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


class EventService:
    """Event management service."""

    async def get_event(self, event_id: str, _db: AsyncSession) -> dict[str, Any]:
        logger.info("Event service called", event_id=event_id)
        return {}
