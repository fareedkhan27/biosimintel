#!/usr/bin/env python3
"""One-time backfill script to populate indication for clinical_trial events with NULL."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Ensure app is importable when running from project root
sys.path.insert(0, str(__file__).replace("/scripts/backfill_indications.py", ""))

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.event import Event

logger = get_logger(__name__)
BATCH_SIZE = 10

INDICATION_PATTERNS = {
    "NSCLC": re.compile(r"non.small.cell.lung|cancer.*lung|lung.*cancer|NSCLC", re.I),
    "Melanoma": re.compile(r"melanoma", re.I),
    "RCC": re.compile(r"renal.cell|carcinoma.*renal|kidney.*cancer", re.I),
    "SCCHN": re.compile(r"squamous.cell.*head|head.*neck.*cancer|SCCHN", re.I),
    "ESCC": re.compile(r"esophageal.*squamous|esophagus.*cancer|ESCC", re.I),
}


class BackfillStats:
    """Simple counter for backfill results."""

    def __init__(self) -> None:
        self.total = 0
        self.updated = 0
        self.skipped = 0
        self.failed = 0

    def summary(self) -> str:
        return (
            f"Backfill complete — Total: {self.total}, "
            f"Updated: {self.updated}, Skipped: {self.skipped}, Failed: {self.failed}"
        )


def _extract_indication_from_payload(raw_payload: Any) -> str | None:
    """Extract indication from a CT.gov raw_payload dict."""
    if not isinstance(raw_payload, dict):
        return None

    protocol = raw_payload.get("protocolSection", {})
    conditions_module = protocol.get("conditionsModule", {})
    conditions = conditions_module.get("conditions", []) or []

    # 1. Structured conditions array
    if conditions:
        for condition in conditions:
            for name, pattern in INDICATION_PATTERNS.items():
                if pattern.search(condition):
                    return name
        return conditions[0]

    # 2. Title + summary fallback
    identification = protocol.get("identificationModule", {})
    title = identification.get("officialTitle", "") or identification.get("briefTitle", "")
    description = protocol.get("descriptionModule", {})
    summary = description.get("briefSummary", "")
    text = f"{title} {summary}"

    if text.strip():
        for name, pattern in INDICATION_PATTERNS.items():
            if pattern.search(text):
                return name

    return None


def _extract_indication_from_text(raw_text: str | None) -> str | None:
    """Extract indication from raw_text via regex patterns."""
    if not raw_text:
        return None
    for name, pattern in INDICATION_PATTERNS.items():
        if pattern.search(raw_text):
            return name
    return None


async def _load_target_events(db: AsyncSession) -> list[Event]:
    """Load clinical_trial events with NULL indication."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.source_document))
        .where(Event.indication.is_(None))
        .where(Event.event_type == "clinical_trial")
        .order_by(Event.created_at.desc())
    )
    events = list(result.scalars().all())
    logger.info("Loaded target events", count=len(events))
    return events


async def _backfill_event(
    event: Event,
    stats: BackfillStats,
    dry_run: bool,
) -> None:
    """Attempt to backfill indication for a single event."""
    stats.total += 1

    try:
        source_doc = event.source_document
        if source_doc is None:
            logger.warning("No source document for event", event_id=str(event.id))
            stats.skipped += 1
            return

        indication: str | None = None

        # Prefer structured payload for CT.gov records
        if source_doc.raw_payload:
            indication = _extract_indication_from_payload(source_doc.raw_payload)

        # Fallback to raw_text regex
        if not indication and source_doc.raw_text:
            indication = _extract_indication_from_text(source_doc.raw_text)

        if not indication:
            logger.info(
                "No indication extractable",
                event_id=str(event.id),
                source_id=str(source_doc.id),
            )
            stats.skipped += 1
            return

        if dry_run:
            logger.info(
                "[DRY RUN] Would update indication",
                event_id=str(event.id),
                indication=indication,
            )
            stats.updated += 1
            return

        event.indication = indication  # type: ignore[assignment]
        logger.info(
            "Updated indication",
            event_id=str(event.id),
            indication=indication,
        )
        stats.updated += 1

    except Exception as exc:
        logger.error(
            "Failed to backfill event",
            event_id=str(event.id),
            error=str(exc),
        )
        stats.failed += 1


async def run_backfill(commit: bool = False) -> BackfillStats:
    """Main backfill routine."""
    configure_logging()
    dry_run = not commit

    if dry_run:
        logger.info("=== DRY RUN MODE — no changes will be committed ===")
    else:
        logger.info("=== COMMIT MODE — changes WILL be persisted ===")

    stats = BackfillStats()

    async with AsyncSessionLocal() as db:
        events = await _load_target_events(db)

        if not events:
            logger.info("No target events found. Nothing to do.")
            return stats

        batch_counter = 0
        for event in events:
            await _backfill_event(event, stats, dry_run)

            if not dry_run and stats.updated > 0:
                batch_counter += 1
                if batch_counter >= BATCH_SIZE:
                    await db.commit()
                    logger.info("Batch committed", batch_size=BATCH_SIZE)
                    batch_counter = 0

        if not dry_run:
            await db.commit()
            logger.info("Final commit completed")

    logger.info(stats.summary())
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill indication for clinical_trial events with NULL indication."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Persist changes to the database (default: dry-run)",
    )
    args = parser.parse_args()

    stats = asyncio.run(run_backfill(commit=args.commit))
    print(f"\n{stats.summary()}")

    if not args.commit:
        print("\nTo apply changes, re-run with: --commit")

    # Exit non-zero if any failures occurred
    sys.exit(0 if stats.failed == 0 else 1)


if __name__ == "__main__":
    main()
