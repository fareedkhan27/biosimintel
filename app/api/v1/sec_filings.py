from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.models.competitor import Competitor
from app.models.sec_filing import SecFiling
from app.schemas.sec_filing import SecFilingResponse
from app.services.sec_edgar import SecEdgarService

router = APIRouter()
edgar = SecEdgarService()
logger = get_logger(__name__)


@router.post("/competitors/{competitor_id}/refresh-sec")
async def refresh_sec_filings(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Fetch latest SEC filings for a competitor and store in DB.
    Avoids duplicates by accession_number.
    Validates SEC company name against competitor name before storing.
    """
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()

    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if not competitor.cik:
        raise HTTPException(status_code=400, detail="Competitor has no CIK configured")

    cik: str = competitor.cik  # type: ignore[assignment]
    competitor_name: str = competitor.canonical_name  # type: ignore[assignment]

    # Fetch submissions and validate company name before proceeding
    submissions = await edgar.get_submissions(cik)
    sec_name = edgar.get_company_name(submissions)

    if sec_name and not edgar._validate_sec_company_name(
        sec_name, competitor_name
    ):
        logger.warning(
            "SEC company name does not match competitor",
            competitor_id=str(competitor_id),
            competitor_name=competitor_name,
            cik=cik,
            sec_name=sec_name,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "competitor_id": str(competitor_id),
                "competitor_name": competitor_name,
                "cik": cik,
                "error": (
                    f"SEC company name '{sec_name}' does not match "
                    f"competitor '{competitor_name}'. CIK may be incorrect."
                ),
                "suggestion": (
                    f"Verify correct CIK at "
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
                ),
            },
        )

    filings = await edgar.get_recent_filings(cik, since_days=180)

    new_count = 0
    for filing in filings:
        existing = await db.execute(
            select(SecFiling).where(
                SecFiling.accession_number == filing["accession_number"]
            )
        )
        if existing.scalar_one_or_none():
            continue

        db_filing = SecFiling(
            competitor_id=competitor_id,
            cik=competitor.cik,
            form_type=filing["form_type"],
            filing_date=datetime.strptime(filing["filing_date"], "%Y-%m-%d"),
            accession_number=filing["accession_number"],
            primary_doc_url=filing["primary_doc_url"],
            title=filing["title"],
        )
        db.add(db_filing)
        new_count += 1

    await db.commit()

    return {
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "cik": competitor.cik,
        "new_filings": new_count,
        "total_filings": len(filings),
    }


@router.get(
    "/competitors/{competitor_id}/sec-filings",
    response_model=list[SecFilingResponse],
)
async def list_sec_filings(
    competitor_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SecFiling]:
    """Return cached SEC filings from DB for a competitor."""
    result = await db.execute(
        select(SecFiling)
        .where(SecFiling.competitor_id == competitor_id)
        .order_by(SecFiling.filing_date.desc())
    )
    filings = result.scalars().all()
    return list(filings)
