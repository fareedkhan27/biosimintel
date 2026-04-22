#!/usr/bin/env python3
"""One-time backfill script to remap existing events with competitor_id = NULL."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Ensure app is importable when running from project root
sys.path.insert(0, str(__file__).replace("/scripts/backfill_competitor_mapping.py", ""))

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.data_provenance import DataProvenance
from app.models.event import Event
from app.services.ingestion.sponsor_mapping import SponsorMappingService

logger = get_logger(__name__)

BATCH_SIZE = 10


def _extract_sponsor_info(raw_payload: Any) -> tuple[str | None, str | None]:
    """Extract sponsor name and class from ClinicalTrials.gov raw payload."""
    if not isinstance(raw_payload, dict):
        return None, None

    protocol = raw_payload.get("protocolSection", {})
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    lead = sponsor_module.get("leadSponsor", {})
    sponsor_name = lead.get("name", "").strip() or None
    sponsor_class = lead.get("class", "").strip() or None
    return sponsor_name, sponsor_class


def _extract_title(raw_payload: Any) -> str | None:
    """Extract brief title from ClinicalTrials.gov raw payload."""
    if not isinstance(raw_payload, dict):
        return None

    protocol = raw_payload.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    title = identification.get("briefTitle", "").strip() or None
    return title


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


async def _load_unmapped_events(db: AsyncSession) -> list[Event]:
    """Load all events with competitor_id IS NULL, eagerly loading source documents."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.source_document))
        .where(Event.competitor_id.is_(None))
        .order_by(Event.created_at.desc())
    )
    events = list(result.scalars().all())
    logger.info("Loaded unmapped events", count=len(events))
    return events


async def _backfill_event(
    db: AsyncSession,
    event: Event,
    mapping_service: SponsorMappingService,
    stats: BackfillStats,
    dry_run: bool,
) -> None:
    """Attempt to backfill a single event."""
    stats.total += 1

    try:
        source_doc = event.source_document
        if source_doc is None:
            logger.warning("No source document for event", event_id=str(event.id))
            stats.skipped += 1
            return

        sponsor_name, sponsor_class = _extract_sponsor_info(source_doc.raw_payload)
        title = _extract_title(source_doc.raw_payload)

        # Fallback: if raw_payload structure is missing, try raw_text
        if sponsor_name is None and source_doc.raw_text:
            # Best-effort: we can't parse raw_text reliably, so skip
            logger.warning(
                "Cannot extract sponsor from raw_payload or raw_text",
                event_id=str(event.id),
                source_id=str(source_doc.id),
            )
            stats.skipped += 1
            return

        if not sponsor_name:
            logger.warning("Empty sponsor name", event_id=str(event.id))
            stats.skipped += 1
            return

        # Ensure competitors are loaded for this event's molecule
        await mapping_service.load_competitors(db, event.molecule_id)

        mapping = mapping_service.map_sponsor_to_competitor(
            sponsor_name, sponsor_class, trial_title=title
        )

        if mapping.blocked:
            logger.info(
                "Skipped: sponsor blocked",
                event_id=str(event.id),
                sponsor=sponsor_name,
                reason=mapping.blocked_reason,
            )
            stats.skipped += 1
            return

        if mapping.competitor is None:
            logger.info(
                "Skipped: no competitor match",
                event_id=str(event.id),
                sponsor=sponsor_name,
                sponsor_class=sponsor_class,
                title=title,
            )
            stats.skipped += 1
            return

        # We have a match
        canonical_name = mapping.competitor.canonical_name
        if dry_run:
            logger.info(
                "[DRY RUN] Would backfill",
                event_id=str(event.id),
                sponsor=sponsor_name,
                mapped_to=canonical_name,
                method=mapping.match_method,
                confidence=mapping.confidence,
            )
            stats.updated += 1
            return

        # Real update
        event.competitor_id = mapping.competitor.id  # type: ignore[assignment]

        provenance = DataProvenance(
            event_id=event.id,
            source_document_id=source_doc.id,
            field_name="competitor_id",
            raw_value=sponsor_name,
            normalized_value=canonical_name,
            extraction_method=f"sponsor_mapping.backfill.{mapping.match_method}",
            confidence=mapping.confidence,
        )
        db.add(provenance)

        logger.info(
            "Backfilled",
            event_id=str(event.id),
            sponsor=sponsor_name,
            mapped_to=canonical_name,
            method=mapping.match_method,
            confidence=mapping.confidence,
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
    mapping_service = SponsorMappingService()

    async with AsyncSessionLocal() as db:
        events = await _load_unmapped_events(db)

        if not events:
            logger.info("No unmapped events found. Nothing to do.")
            return stats

        batch_counter = 0
        for event in events:
            await _backfill_event(db, event, mapping_service, stats, dry_run)

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
        description="Backfill competitor_id for existing events with NULL mappings."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Persist changes to the database (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Log what would change without writing (default)",
    )
    args = parser.parse_args()

    # --commit overrides --dry-run
    commit = args.commit

    stats = asyncio.run(run_backfill(commit=commit))
    print(f"\n{stats.summary()}")

    if not commit:
        print("\nTo apply changes, re-run with: --commit")

    # Exit non-zero if any failures occurred
    sys.exit(0 if stats.failed == 0 else 1)


if __name__ == "__main__":
    main()
