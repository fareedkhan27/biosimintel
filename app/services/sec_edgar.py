from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SecEdgarService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={"User-Agent": settings.SEC_EDGAR_USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )
        self.base_url = "https://data.sec.gov"

    def _pad_cik(self, cik: str) -> str:
        """Zero-pad CIK to 10 digits."""
        return cik.strip().zfill(10)

    def _normalize_name(self, name: str) -> str:
        """Normalize company name for comparison."""
        return name.lower().replace("'", "").replace(".", "").replace(",", "").strip()

    def _validate_sec_company_name(self, sec_name: str, competitor_name: str) -> bool:
        """
        Returns True if SEC name matches or is a close fuzzy match to competitor name.
        Uses simple containment or fuzzy ratio.
        """
        sec_normalized = self._normalize_name(sec_name)
        comp_normalized = self._normalize_name(competitor_name)

        # Direct containment
        if comp_normalized in sec_normalized or sec_normalized in comp_normalized:
            return True

        # Fuzzy match threshold (e.g., 70%)
        ratio = SequenceMatcher(None, sec_normalized, comp_normalized).ratio()
        return ratio > 0.70

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch recent submissions metadata for a CIK."""
        padded = self._pad_cik(cik)
        url = f"{self.base_url}/submissions/CIK{padded}.json"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def get_company_name(self, submissions: dict[str, Any]) -> str | None:
        """Extract company name from SEC submissions response."""
        return submissions.get("name")

    async def get_recent_filings(
        self,
        cik: str,
        form_types: list[str] | None = None,
        since_days: int = 90
    ) -> list[dict[str, Any]]:
        """
        Return recent filings filtered by form type and date.
        Defaults to 10-K, 10-Q, 8-K from last 90 days.
        """
        if form_types is None:
            form_types = ["10-K", "10-Q", "8-K"]

        data = await self.get_submissions(cik)
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accession = recent.get("accessionNumber", [])
        primary_doc = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        cutoff = datetime.now() - timedelta(days=since_days)
        results = []

        for i, form in enumerate(forms):
            if form not in form_types:
                continue
            filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
            if filing_date < cutoff:
                continue

            acc = accession[i].replace("-", "")
            doc = primary_doc[i]
            cik_int = int(cik)
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"

            results.append({
                "form_type": form,
                "filing_date": dates[i],
                "accession_number": accession[i],
                "primary_doc_url": doc_url,
                "title": descriptions[i] if i < len(descriptions) else None,
            })

        return results

    async def close(self) -> None:
        await self.client.aclose()
