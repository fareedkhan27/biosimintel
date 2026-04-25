from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.combo import ComboCapability, CompetitorMoleculeAssignment
from app.models.competitor import Competitor
from app.models.molecule import Molecule

logger = get_logger(__name__)

THREAT_MAP = {
    ComboCapability.FULL: "HIGH",
    ComboCapability.PARTIAL: "MODERATE",
    ComboCapability.NONE: "LOW",
}


class ComboIntelligenceService:
    """Service for combo-tracking intelligence."""

    async def get_competitor_combo_threat(self, competitor_id: UUID) -> dict[str, Any]:
        """Return combo threat assessment for a single competitor."""
        async with AsyncSessionLocal() as db:
            comp_result = await db.execute(
                select(Competitor).where(Competitor.id == competitor_id)
            )
            competitor = comp_result.scalar_one_or_none()
            if competitor is None:
                return {
                    "competitor": "",
                    "nivolumab_asset": None,
                    "ipilimumab_asset": None,
                    "combo_capability": ComboCapability.NONE.value,
                    "threat_level": "LOW",
                }

            nivo_result = await db.execute(
                select(Molecule).where(Molecule.inn == "nivolumab")
            )
            nivo = nivo_result.scalar_one_or_none()
            ipi_result = await db.execute(
                select(Molecule).where(Molecule.inn == "ipilimumab")
            )
            ipi = ipi_result.scalar_one_or_none()

            nivo_id = nivo.id if nivo else None
            ipi_id = ipi.id if ipi else None

            assignments_result = await db.execute(
                select(CompetitorMoleculeAssignment).where(
                    CompetitorMoleculeAssignment.competitor_id == competitor_id
                )
            )
            assignments = assignments_result.scalars().all()

            return self._build_threat_dict(
                competitor.canonical_name,  # type: ignore[arg-type]
                assignments,
                nivo_id,  # type: ignore[arg-type]
                ipi_id,  # type: ignore[arg-type]
            )

    def _build_threat_dict(
        self,
        competitor_name: str,
        assignments: Any,
        nivo_id: UUID | None,
        ipi_id: UUID | None,
    ) -> dict[str, Any]:
        nivo_asset: str | None = None
        ipi_asset: str | None = None
        combo_capability = ComboCapability.NONE

        for assignment in assignments:
            if nivo_id and assignment.molecule_id == nivo_id:
                nivo_asset = assignment.asset_name
            if ipi_id and assignment.molecule_id == ipi_id:
                ipi_asset = assignment.asset_name
            if assignment.combo_capability == ComboCapability.FULL:
                combo_capability = ComboCapability.FULL
            elif (
                assignment.combo_capability == ComboCapability.PARTIAL
                and combo_capability != ComboCapability.FULL
            ):
                combo_capability = ComboCapability.PARTIAL

        return {
            "competitor": competitor_name,
            "nivolumab_asset": nivo_asset,
            "ipilimumab_asset": ipi_asset,
            "combo_capability": combo_capability.value,
            "threat_level": THREAT_MAP[combo_capability],
        }

    async def get_combo_threat_matrix(self) -> list[dict[str, Any]]:
        """Return all competitors ranked by combo threat level (HIGH first)."""
        async with AsyncSessionLocal() as db:
            # Resolve molecule IDs once
            nivo_result = await db.execute(
                select(Molecule).where(Molecule.inn == "nivolumab")
            )
            nivo = nivo_result.scalar_one_or_none()
            ipi_result = await db.execute(
                select(Molecule).where(Molecule.inn == "ipilimumab")
            )
            ipi = ipi_result.scalar_one_or_none()
            nivo_id = nivo.id if nivo else None
            ipi_id = ipi.id if ipi else None

            # Fetch all competitors and assignments in bulk
            comp_result = await db.execute(select(Competitor))
            competitors = comp_result.scalars().all()

            assignments_result = await db.execute(
                select(CompetitorMoleculeAssignment)
            )
            all_assignments = assignments_result.scalars().all()

            # Group assignments by competitor
            assignments_by_competitor: dict[UUID, list[Any]] = {}
            for a in all_assignments:
                cid: UUID = a.competitor_id  # type: ignore[assignment]
                assignments_by_competitor.setdefault(cid, []).append(a)

            matrix = []
            for competitor in competitors:
                comp_id: UUID = competitor.id  # type: ignore[assignment]
                comp_assignments = assignments_by_competitor.get(comp_id, [])
                threat = self._build_threat_dict(
                    competitor.canonical_name,  # type: ignore[arg-type]
                    comp_assignments,
                    nivo_id,  # type: ignore[arg-type]
                    ipi_id,  # type: ignore[arg-type]
                )
                matrix.append(threat)

        threat_order = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
        matrix.sort(key=lambda x: threat_order.get(x["threat_level"], 3))
        return matrix
