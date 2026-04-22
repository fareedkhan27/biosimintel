from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.molecule import Molecule

logger = get_logger(__name__)


class SECEDGARService:
    """Deterministic ingestion from SEC EDGAR."""

    def __init__(self) -> None:
        self.base_url = str(settings.SEC_EDGAR_BASE_URL)

    async def sync(self, molecule: Molecule, _db: AsyncSession) -> None:
        logger.info("SEC EDGAR sync not yet implemented", molecule=molecule.molecule_name)
        # Placeholder for SEC EDGAR integration
