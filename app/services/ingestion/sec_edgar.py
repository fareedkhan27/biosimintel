from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.molecule import Molecule
from app.models.source_document import SourceDocument

logger = get_logger(__name__)

SEC_SOURCE_NAME = "sec_edgar"
SEC_SOURCE_TYPE = "regulatory_filing"
RELEVANT_FORMS = {"8-K", "10-K", "10-Q"}

BIOSIMILAR_KEYWORD_RE = re.compile(
    r"\b(biosimilar|biosimilarity|abp 206|tishtha|xdivane|ba1104|jpb898|hlx18|mb11|nivolumab biosimilar)\b",
    re.IGNORECASE,
)


class SECEDGARService:
    """Deterministic ingestion from SEC EDGAR filings."""

    def __init__(self) -> None:
        self.submissions_url = str(settings.SEC_EDGAR_SUBMISSIONS_URL)
        self.user_agent = str(settings.SEC_EDGAR_USER_AGENT)
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": self.user_agent},
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_submissions(self, padded_cik: str) -> dict[str, Any]:
        """Fetch SEC EDGAR submissions for a CIK with retries."""
        url = f"{self.submissions_url}{padded_cik}.json"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def sync(self, molecule: Molecule, db: AsyncSession) -> dict[str, Any]:
        """Sync SEC EDGAR filings for competitors tracking a molecule.

        Looks up competitors with CIKs, fetches their recent filings,
        filters for biosimilar-related 8-K / 10-K / 10-Q submissions,
        and creates SourceDocument rows for each match.

        Returns a summary dict with counts of created, skipped, and matched
        filings.
        """
        logger.info(
            "Starting SEC EDGAR sync",
            molecule=molecule.molecule_name,
        )

        # Load competitors with CIKs for this molecule
        competitors_result = await db.execute(
            select(Competitor).where(
                Competitor.molecule_id == molecule.id,
                Competitor.cik.isnot(None),
            )
        )
        competitors = list(competitors_result.scalars().all())

        if not competitors:
            logger.info(
                "No competitors with CIKs found for molecule",
                molecule=molecule.molecule_name,
            )
            return {
                "created": 0,
                "skipped_duplicates": 0,
                "matched_filings": 0,
                "competitors_checked": 0,
            }

        created_count = 0
        skipped_count = 0
        matched_count = 0

        for competitor in competitors:
            cik = competitor.cik or ""
            padded_cik = cik.zfill(10)

            try:
                data = await self._fetch_submissions(padded_cik)
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.error(
                    "SEC EDGAR fetch failed for competitor",
                    competitor=competitor.canonical_name,
                    cik=padded_cik,
                    error=str(exc),
                )
                continue

            recent = data.get("filings", {}).get("recent", {})
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            forms = recent.get("form", [])
            primary_docs = recent.get("primaryDocument", [])
            descriptions = recent.get("primaryDocDescription", [])

            for idx, accession_number in enumerate(accession_numbers):
                form = forms[idx] if idx < len(forms) else ""
                if form not in RELEVANT_FORMS:
                    continue

                description = descriptions[idx] if idx < len(descriptions) else ""
                title_text = f"{form} {description}".strip()

                if not BIOSIMILAR_KEYWORD_RE.search(title_text):
                    continue

                matched_count += 1
                filing_date = filing_dates[idx] if idx < len(filing_dates) else None
                primary_doc = primary_docs[idx] if idx < len(primary_docs) else ""

                # Deduplication check
                existing = await db.execute(
                    select(SourceDocument).where(
                        SourceDocument.source_name == SEC_SOURCE_NAME,
                        SourceDocument.external_id == accession_number,
                    )
                )
                if existing.scalar_one_or_none():
                    logger.info(
                        "Skipping duplicate SEC filing",
                        accession_number=accession_number,
                    )
                    skipped_count += 1
                    continue

                # Build SEC document URL
                accession_no_dashes = accession_number.replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_doc}"
                )

                source_doc = SourceDocument(
                    source_name=SEC_SOURCE_NAME,
                    source_type=SEC_SOURCE_TYPE,
                    external_id=accession_number,
                    title=f"{form} filing - {competitor.canonical_name}",
                    url=doc_url,
                    published_at=filing_date,
                    raw_payload={
                        "cik": cik,
                        "entity_name": data.get("entityName", ""),
                        "form": form,
                        "filing_date": filing_date,
                        "accession_number": accession_number,
                        "primary_document": primary_doc,
                        "description": description,
                    },
                    processing_status="pending",
                    molecule_id=molecule.id,
                )
                db.add(source_doc)
                await db.flush()

                logger.info(
                    "Created SEC EDGAR source document",
                    competitor=competitor.canonical_name,
                    form=form,
                    accession_number=accession_number,
                )
                created_count += 1

        logger.info(
            "SEC EDGAR sync completed",
            molecule=molecule.molecule_name,
            created=created_count,
            skipped_duplicates=skipped_count,
            matched=matched_count,
            competitors_checked=len(competitors),
        )

        return {
            "created": created_count,
            "skipped_duplicates": skipped_count,
            "matched_filings": matched_count,
            "competitors_checked": len(competitors),
        }

    async def close(self) -> None:
        await self.client.aclose()
