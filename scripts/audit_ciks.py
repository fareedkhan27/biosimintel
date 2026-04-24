"""Audit competitor CIKs against SEC EDGAR API.

For each competitor with a CIK, fetch the company name from SEC and compare
with the competitor's canonical name. Flag mismatches.

Usage:
    PYTHONPATH=. python scripts/audit_ciks.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import engine
from app.models.competitor import Competitor

logger = get_logger(__name__)

USER_AGENT = settings.SEC_EDGAR_USER_AGENT


def _normalize(name: str) -> str:
    return name.lower().replace("'", "").replace(".", "").replace(",", "").strip()


def _name_matches(sec_name: str, comp_name: str) -> bool:
    sec_norm = _normalize(sec_name)
    comp_norm = _normalize(comp_name)
    if comp_norm in sec_norm or sec_norm in comp_norm:
        return True
    from difflib import SequenceMatcher

    ratio = SequenceMatcher(None, sec_norm, comp_norm).ratio()
    return ratio > 0.70


async def _fetch_sec_name(client: httpx.AsyncClient, cik: str) -> str | None:
    padded = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    try:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
        return data.get("name")
    except Exception as exc:
        logger.error("Failed to fetch SEC data", cik=cik, error=str(exc))
        return None


async def audit_ciks() -> list[dict[str, str]]:
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    mismatches: list[dict[str, str]] = []

    async with async_session() as db:
        result = await db.execute(select(Competitor).where(Competitor.cik.isnot(None)))
        competitors = list(result.scalars().all())

        logger.info("Starting CIK audit", total_competitors=len(competitors))

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for competitor in competitors:
                cik = competitor.cik or ""
                sec_name = await _fetch_sec_name(client, cik)
                if sec_name is None:
                    continue

                if not _name_matches(sec_name, competitor.canonical_name):
                    mismatch = {
                        "competitor_id": str(competitor.id),
                        "competitor_name": competitor.canonical_name,
                        "cik": cik,
                        "sec_name": sec_name,
                    }
                    mismatches.append(mismatch)
                    logger.warning(
                        "CIK mismatch detected",
                        **mismatch,
                    )
                else:
                    logger.info(
                        "CIK verified OK",
                        competitor_name=competitor.canonical_name,
                        cik=cik,
                        sec_name=sec_name,
                    )

    return mismatches


async def main() -> int:
    mismatches = await audit_ciks()

    print(f"\n{'=' * 60}")
    print(f"CIK Audit Complete: {len(mismatches)} mismatch(es) found")
    print(f"{'=' * 60}\n")

    for m in mismatches:
        print(
            f"  - {m['competitor_name']} (CIK: {m['cik']})\n"
            f"    SEC name: {m['sec_name']}\n"
            f"    Competitor ID: {m['competitor_id']}"
        )

    if mismatches:
        print("\nPlease verify and correct the flagged CIKs.")
        return 1

    print("All competitor CIKs verified successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
