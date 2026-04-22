from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import IngestionException
from app.core.logging import get_logger
from app.models.molecule import Molecule
from app.models.source_document import SourceDocument

logger = get_logger(__name__)

EMA_SOURCE_NAME = "ema_medicines_json"
EMA_SOURCE_TYPE = "regulatory_database"


class EMAService:
    """Deterministic ingestion from EMA Medicines JSON report."""

    def __init__(self) -> None:
        self.base_url = str(settings.EMA_API_BASE_URL)
        self.client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_report(self) -> dict[str, Any]:
        """Download the EMA medicines JSON report with retries."""
        response = await self.client.get(self.base_url)
        response.raise_for_status()
        return response.json()

    async def sync(self, molecule: Molecule, db: AsyncSession) -> dict[str, Any]:
        """Sync EMA medicines records for a molecule.

        Downloads the full EMA JSON report, filters for records whose
        active_substance matches any of the molecule's search terms, and
        creates SourceDocument rows for each match.

        Returns a summary dict with counts of created, skipped, filtered,
        and total records.
        """
        search_terms: list[str] = molecule.search_terms or [molecule.molecule_name]  # type: ignore[assignment]
        search_terms_lower = [t.lower() for t in search_terms]

        logger.info(
            "Starting EMA sync",
            molecule=molecule.molecule_name,
            search_terms=search_terms,
        )

        try:
            data = await self._fetch_report()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.error("EMA report download failed", error=str(exc))
            raise IngestionException(f"EMA report download failed: {exc}") from exc

        meta = data.get("meta", {})
        records = data.get("data", [])
        api_total = meta.get("total_records", len(records))

        if not records:
            logger.warning("EMA report returned no records")
            return {
                "created": 0,
                "skipped_duplicates": 0,
                "filtered_total": 0,
                "api_total_records": api_total,
            }

        created_count = 0
        skipped_count = 0
        filtered_count = 0

        for record in records:
            active_substance = record.get("active_substance", "") or ""
            active_lower = active_substance.lower()

            if not any(term in active_lower for term in search_terms_lower):
                continue

            filtered_count += 1
            ema_product_number = record.get("ema_product_number", "")
            name_of_medicine = record.get("name_of_medicine", "")

            # Deduplication check
            existing = await db.execute(
                select(SourceDocument).where(
                    SourceDocument.source_name == EMA_SOURCE_NAME,
                    SourceDocument.external_id == ema_product_number,
                )
            )
            if existing.scalar_one_or_none():
                logger.info(
                    "Skipping duplicate EMA record",
                    ema_product_number=ema_product_number,
                )
                skipped_count += 1
                continue

            published_at = self._parse_date(
                record.get("marketing_authorisation_date", "")
            )

            source_doc = SourceDocument(
                source_name=EMA_SOURCE_NAME,
                source_type=EMA_SOURCE_TYPE,
                external_id=ema_product_number,
                title=name_of_medicine,
                url=record.get("medicine_url", ""),
                published_at=published_at,
                raw_payload=record,
                processing_status="pending",
                molecule_id=molecule.id,
            )
            db.add(source_doc)
            await db.flush()

            logger.info(
                "Created EMA source document",
                name=name_of_medicine,
                ema_product_number=ema_product_number,
            )
            created_count += 1

        logger.info(
            "EMA sync completed",
            molecule=molecule.molecule_name,
            created=created_count,
            skipped_duplicates=skipped_count,
            filtered=filtered_count,
            api_total=api_total,
        )

        return {
            "created": created_count,
            "skipped_duplicates": skipped_count,
            "filtered_total": filtered_count,
            "api_total_records": api_total,
        }

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse EMA date format 'DD/MM/YYYY' to UTC datetime."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").replace(tzinfo=UTC)
        except ValueError:
            logger.warning("Unable to parse EMA date", date_str=date_str)
            return None

    async def close(self) -> None:
        await self.client.aclose()
