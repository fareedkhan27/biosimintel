#!/usr/bin/env python3
"""One-time backfill script to create GeoSignals for all existing events."""

from __future__ import annotations

import asyncio
import sys
from typing import cast
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, "/Users/fareedkhan/Dev/Biosim")

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.event import Event
from app.models.signal import GeoSignal
from app.services.signal_service import SignalIntelligenceService

logger = get_logger(__name__)


async def backfill_signals() -> None:
    configure_logging()
    logger.info("Starting GeoSignal backfill")

    async with AsyncSessionLocal() as db:
        event_result = await db.execute(select(Event))
        events = list(event_result.scalars().all())
        logger.info("Loaded events", count=len(events))

        signal_result = await db.execute(select(GeoSignal.event_id))
        existing_event_ids = {
            row[0] for row in signal_result.all() if row[0] is not None
        }
        logger.info("Existing GeoSignals", count=len(existing_event_ids))

    svc = SignalIntelligenceService()
    processed = 0
    created = 0
    skipped = 0

    for idx, event in enumerate(events):
        if event.id in existing_event_ids:
            skipped += 1
            continue

        try:
            await svc.ingest_and_tag_event(cast(UUID, event.id))
            created += 1
        except Exception as exc:
            logger.error(
                "Failed to ingest event",
                event_id=str(event.id),
                error=str(exc),
            )

        processed += 1
        if (idx + 1) % 10 == 0:
            logger.info(
                "Progress",
                processed=processed,
                created=created,
                skipped=skipped,
            )

    logger.info(
        "Backfill complete",
        total_events=len(events),
        processed=processed,
        created=created,
        skipped=skipped,
    )


if __name__ == "__main__":
    asyncio.run(backfill_signals())
