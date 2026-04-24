from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.molecule import Molecule
from app.models.patent_cliff import PatentCliff
from app.schemas.regulatory_risk import PatentCliffEntry, RegulatoryRiskProfile

PATHWAY_WEIGHTS: dict[str, float] = {
    "351(k)": 0.35,
    "aBLA": 0.25,
    "BPCIA": 0.25,
    "standard": 0.15,
}


def patent_cliff_score(days_to_expiry: int) -> int:
    if days_to_expiry <= 0:
        return 100
    if days_to_expiry <= 365:
        return 80
    if days_to_expiry <= 730:
        return 50
    if days_to_expiry <= 1095:
        return 25
    return 0


async def calculate_regulatory_risk_weights(
    molecule_id: UUID,
    db: AsyncSession,
) -> RegulatoryRiskProfile:
    """Calculate regulatory risk profile including patent cliff overlay."""
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Molecule")

    # Fetch patent cliffs
    patent_result = await db.execute(
        select(PatentCliff).where(PatentCliff.molecule_id == molecule_id)
    )
    patents = list(patent_result.scalars().all())

    # Competitor activity per indication is derived from events below

    # For patent cliffs, determine if competitors are active in that indication
    # We need events to map competitor activity by indication
    from app.models.event import Event
    event_result = await db.execute(
        select(Event)
        .where(Event.molecule_id == molecule_id)
        .where(Event.indication.isnot(None))
    )
    events = list(event_result.scalars().all())
    indication_with_activity: set[str] = set()
    for evt in events:
        if evt.indication:
            indication_with_activity.add(evt.indication.strip())

    today = datetime.now(UTC).date()
    patent_entries: list[PatentCliffEntry] = []
    for p in patents:
        days_to_expiry = (p.expiry_date - today).days if p.expiry_date else -9999
        patent_entries.append(
            PatentCliffEntry(
                indication=p.indication,  # type: ignore[arg-type]
                patent_type=p.patent_type,  # type: ignore[arg-type]
                patent_number=p.patent_number,  # type: ignore[arg-type]
                expiry_date=p.expiry_date,  # type: ignore[arg-type]
                territory=p.territory,  # type: ignore[arg-type]
                days_to_expiry=days_to_expiry,
                cliff_score=patent_cliff_score(days_to_expiry),
                competitors_active=p.indication in indication_with_activity,
            )
        )

    return RegulatoryRiskProfile(
        molecule_id=molecule_id,
        patent_cliffs=patent_entries,
        pathway_weights=PATHWAY_WEIGHTS,
        generated_at=datetime.now(UTC),
    )
