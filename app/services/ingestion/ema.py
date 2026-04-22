from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.molecule import Molecule

logger = get_logger(__name__)


class EMAService:
    """Deterministic ingestion from EMA Medicines Search API."""

    def __init__(self) -> None:
        self.base_url = str(settings.EMA_API_BASE_URL)

    async def sync(self, molecule: Molecule, _db: AsyncSession) -> None:
        logger.info("EMA sync not yet implemented", molecule=molecule.molecule_name)
        # Placeholder for EMA API integration
