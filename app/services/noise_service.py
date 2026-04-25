from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.geo import Country, Region
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal, NoiseSourceType, NoiseVerificationStatus
from app.models.signal import Confidence, GeoSignal

logger = get_logger(__name__)


class NoiseBlockService:
    """Manage Tier 3 (unconfirmed) noise signals: press, social, conference, analyst, rumor."""

    async def ingest_noise(
        self,
        raw_text: str,
        source_type: str,
        source_url: str | None = None,
        source_author: str | None = None,
    ) -> NoiseSignal:
        async with AsyncSessionLocal() as db:
            try:
                st = NoiseSourceType(source_type.lower())
            except ValueError:
                st = NoiseSourceType.RUMOR

            geo_signal_id: UUID | None = None
            try:
                geo_signal_id = await self._try_link_noise(db, raw_text)
            except Exception as exc:
                logger.warning("Noise auto-link failed", error=str(exc))

            expires_at = datetime.now(UTC) + timedelta(days=7)

            noise = NoiseSignal(
                geo_signal_id=geo_signal_id,
                raw_text=raw_text,
                source_type=st,
                source_url=source_url,
                source_author=source_author,
                flagged_at=datetime.now(UTC),
                verification_status=NoiseVerificationStatus.PENDING,
                expires_at=expires_at,
            )
            db.add(noise)
            await db.commit()
            await db.refresh(noise)
            logger.info(
                "Noise signal ingested",
                noise_id=str(cast(UUID, noise.id)),
                geo_signal_id=str(geo_signal_id) if geo_signal_id else None,
            )
            return noise

    async def _try_link_noise(
        self, db: AsyncSession, raw_text: str
    ) -> UUID | None:
        text_lower = raw_text.lower()

        comp_result = await db.execute(select(Competitor))
        competitors = comp_result.scalars().all()

        matched_competitor_id: UUID | None = None
        for competitor in competitors:
            name = cast(str | None, competitor.canonical_name)
            if name and name.lower() in text_lower:
                matched_competitor_id = cast(UUID, competitor.id)
                break

        if matched_competitor_id is None:
            return None

        signal_result = await db.execute(
            select(GeoSignal)
            .where(GeoSignal.competitor_id == matched_competitor_id)
            .order_by(GeoSignal.created_at.desc())
            .limit(1)
        )
        geo_signal = signal_result.scalar_one_or_none()
        if geo_signal:
            return cast(UUID, geo_signal.id)
        return None

    async def verify_noise(
        self,
        noise_id: UUID,
        verification_notes: str,
        verified_by: str,
    ) -> NoiseSignal:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NoiseSignal).where(NoiseSignal.id == noise_id)
            )
            noise = result.scalar_one_or_none()
            if noise is None:
                raise ValueError(f"NoiseSignal not found: {noise_id}")

            noise.verification_status = NoiseVerificationStatus.VERIFIED  # type: ignore[assignment]
            noise.verified_at = datetime.now(UTC)  # type: ignore[assignment]
            noise.verified_by = verified_by  # type: ignore[assignment]
            noise.verification_notes = verification_notes  # type: ignore[assignment]

            if noise.geo_signal_id:
                gs_result = await db.execute(
                    select(GeoSignal).where(GeoSignal.id == noise.geo_signal_id)
                )
                geo_signal = gs_result.scalar_one_or_none()
                if geo_signal:
                    geo_signal.tier = 2  # type: ignore[assignment]
                    geo_signal.confidence = Confidence.PROBABLE  # type: ignore[assignment]
                    geo_signal.expires_at = None  # type: ignore[assignment]

            await db.commit()
            await db.refresh(noise)
            logger.info("Noise signal verified", noise_id=str(noise_id), by=verified_by)
            return noise

    async def dismiss_noise(
        self,
        noise_id: UUID,
        dismissed_by: str,
    ) -> NoiseSignal:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NoiseSignal).where(NoiseSignal.id == noise_id)
            )
            noise = result.scalar_one_or_none()
            if noise is None:
                raise ValueError(f"NoiseSignal not found: {noise_id}")

            noise.verification_status = NoiseVerificationStatus.DISMISSED  # type: ignore[assignment]
            noise.dismissed_at = datetime.now(UTC)  # type: ignore[assignment]
            noise.dismissed_by = dismissed_by  # type: ignore[assignment]

            await db.commit()
            await db.refresh(noise)
            logger.info("Noise signal dismissed", noise_id=str(noise_id), by=dismissed_by)
            return noise

    async def escalate_noise(self, noise_id: UUID) -> NoiseSignal:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NoiseSignal).where(NoiseSignal.id == noise_id)
            )
            noise = result.scalar_one_or_none()
            if noise is None:
                raise ValueError(f"NoiseSignal not found: {noise_id}")

            current_count = cast(int | None, noise.escalation_count) or 0
            noise.escalation_count = current_count + 1  # type: ignore[assignment]

            if current_count + 1 >= 3:
                noise.verification_status = NoiseVerificationStatus.VERIFIED  # type: ignore[assignment]
                noise.verified_at = datetime.now(UTC)  # type: ignore[assignment]
                noise.verified_by = "auto_escalation"  # type: ignore[assignment]

                if noise.geo_signal_id:
                    gs_result = await db.execute(
                        select(GeoSignal).where(GeoSignal.id == noise.geo_signal_id)
                    )
                    geo_signal = gs_result.scalar_one_or_none()
                    if geo_signal:
                        geo_signal.tier = 2  # type: ignore[assignment]
                        geo_signal.confidence = Confidence.PROBABLE  # type: ignore[assignment]
                        geo_signal.expires_at = None  # type: ignore[assignment]

            await db.commit()
            await db.refresh(noise)
            logger.info(
                "Noise signal escalated",
                noise_id=str(noise_id),
                count=current_count + 1,
            )
            return noise

    async def expire_old_noise(self) -> int:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            result = await db.execute(
                select(NoiseSignal).where(
                    NoiseSignal.expires_at < now,
                    NoiseSignal.verification_status == NoiseVerificationStatus.PENDING,
                )
            )
            expired = list(result.scalars().all())
            for noise in expired:
                noise.verification_status = NoiseVerificationStatus.EXPIRED  # type: ignore[assignment]

            await db.commit()
            logger.info("Expired old noise signals", count=len(expired))
            return len(expired)

    async def get_noise_digest(
        self,
        region_code: str,
        since: datetime,
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            region_result = await db.execute(
                select(Region).where(Region.code == region_code.upper())
            )
            region = region_result.scalar_one_or_none()
            if region is None:
                return []

            country_result = await db.execute(
                select(Country.id).where(Country.region_id == region.id)
            )
            region_country_ids = [row[0] for row in country_result.all()]
            if not region_country_ids:
                return []

            noise_result = await db.execute(
                select(NoiseSignal, GeoSignal)
                .join(GeoSignal, NoiseSignal.geo_signal_id == GeoSignal.id, isouter=True)
                .where(NoiseSignal.verification_status == NoiseVerificationStatus.PENDING)
                .where(NoiseSignal.flagged_at >= since)
                .order_by(NoiseSignal.flagged_at.desc())
            )
            rows = noise_result.all()

            digest: list[dict[str, Any]] = []
            now = datetime.now(UTC)

            for noise, geo_signal in rows:
                if geo_signal and geo_signal.country_ids:
                    if not any(cid in region_country_ids for cid in geo_signal.country_ids):
                        continue
                elif geo_signal is None:
                    pass
                else:
                    continue

                days_until_expiry = 0
                expires = cast(datetime | None, noise.expires_at)
                if expires:
                    delta = expires - now
                    days_until_expiry = max(0, delta.days)

                linked_competitor = ""
                linked_molecule = ""
                if geo_signal:
                    if geo_signal.competitor_id:
                        comp_result = await db.execute(
                            select(Competitor).where(Competitor.id == geo_signal.competitor_id)
                        )
                        comp = comp_result.scalar_one_or_none()
                        if comp:
                            linked_competitor = cast(str, comp.canonical_name)
                    if geo_signal.molecule_id:
                        mol_result = await db.execute(
                            select(Molecule).where(Molecule.id == geo_signal.molecule_id)
                        )
                        mol = mol_result.scalar_one_or_none()
                        if mol:
                            linked_molecule = cast(str, mol.molecule_name)

                digest.append({
                    "id": str(cast(UUID, noise.id)),
                    "raw_text": cast(str, noise.raw_text),
                    "source_type": cast(str, noise.source_type.value),
                    "source_author": cast(str, noise.source_author) or "",
                    "flagged_at": (
                        cast(datetime, noise.flagged_at).isoformat()
                        if noise.flagged_at else ""
                    ),
                    "days_until_expiry": days_until_expiry,
                    "escalation_count": cast(int | None, noise.escalation_count) or 0,
                    "linked_competitor": linked_competitor,
                    "linked_molecule": linked_molecule,
                })

            return digest
