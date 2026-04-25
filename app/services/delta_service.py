from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.event import Event
from app.models.signal import GeoSignal

logger = get_logger(__name__)


class DeltaDetectionService:
    """Detect new and updated events since a given timestamp."""

    async def detect_changes_since(self, yesterday: datetime) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Event).where(Event.updated_at >= yesterday)
            )
            events = result.scalars().all()

            for event in events:
                signal_result = await db.execute(
                    select(GeoSignal).where(
                        GeoSignal.event_id == event.id,
                        GeoSignal.created_at < yesterday,
                    )
                )
                existing_signal = signal_result.scalar_one_or_none()

                competitor_name = ""
                if event.competitor_id:
                    comp_result = await db.execute(
                        select(Competitor).where(Competitor.id == event.competitor_id)
                    )
                    competitor = comp_result.scalar_one_or_none()
                    if competitor:
                        competitor_name = cast(str, competitor.canonical_name) or ""

                if existing_signal:
                    delta_note = f"Updated: {event.event_type} status changed"
                else:
                    delta_note = f"New event: {event.event_type} for {competitor_name}"

                changes.append(
                    {
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "competitor_name": competitor_name,
                        "delta_note": delta_note,
                        "updated_at": (
                            event.updated_at.isoformat() if event.updated_at else None
                        ),
                    }
                )

            logger.info("Delta detection complete", changes=len(changes))
            return changes
