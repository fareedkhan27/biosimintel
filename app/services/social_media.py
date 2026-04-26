from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal, NoiseSourceType, NoiseVerificationStatus
from app.models.social_media import SocialMediaRaw
from app.schemas.social_media import SocialMediaIngestResult, SocialMediaRawCreate

logger = get_logger(__name__)


class SocialMediaService:
    """Ingest social media posts and always route to NoiseSignal (never auto-verify)."""

    async def ingest_social_media(
        self,
        data: SocialMediaRawCreate,
        db: AsyncSession,
    ) -> SocialMediaIngestResult:
        # Step 1 — Build keyword maps dynamically from DB
        molecule_map = await self._build_molecule_map(db)
        competitor_map = await self._build_competitor_map(db)

        combined = data.post_text.lower()

        # Match molecule
        molecule_id: UUID | None = None
        matched_molecule_keywords: list[str] = []
        for kw, mid in molecule_map.items():
            if kw in combined:
                molecule_id = mid
                matched_molecule_keywords.append(kw)
                break

        # Match competitor
        competitor_id: UUID | None = None
        matched_competitor_keywords: list[str] = []
        for kw, cid in competitor_map.items():
            if kw in combined:
                competitor_id = cid
                matched_competitor_keywords.append(kw)
                break

        # Step 2 — Confidence scoring (always low, hard cap)
        max_confidence = getattr(settings, "SOCIAL_MEDIA_MAX_CONFIDENCE", 55)
        if molecule_id and competitor_id:
            confidence = min(55, max_confidence)
        elif competitor_id:
            confidence = min(50, max_confidence)
        else:
            confidence = min(40, max_confidence)

        # Step 3 — Always create NoiseSignal (never GeoSignal)
        expiry_days = getattr(settings, "SOCIAL_MEDIA_NOISE_EXPIRY_DAYS", 7)
        expires_at = datetime.now(UTC) + timedelta(days=expiry_days)

        all_keywords = matched_molecule_keywords + matched_competitor_keywords
        matched_keywords_str = ", ".join(all_keywords) if all_keywords else None

        noise = NoiseSignal(
            geo_signal_id=None,
            raw_text=data.post_text,
            source_type=NoiseSourceType.SOCIAL,
            source_url=data.post_url,
            source_author=data.author,
            flagged_at=datetime.now(UTC),
            verification_status=NoiseVerificationStatus.PENDING,
            expires_at=expires_at,
        )
        db.add(noise)
        await db.flush()
        await db.refresh(noise)
        noise_signal_id = cast(UUID, noise.id)

        # Store the raw social media record
        raw_record = SocialMediaRaw(
            source_platform=data.source_platform,
            post_url=data.post_url,
            author=data.author,
            post_text=data.post_text,
            published_date=data.published_date,
            engagement_score=data.engagement_score,
            matched_keywords=matched_keywords_str,
            molecule_id=molecule_id,
            competitor_id=competitor_id,
            noise_signal_id=noise_signal_id,
        )
        db.add(raw_record)
        await db.commit()
        await db.refresh(raw_record)

        logger.info(
            "Social media ingested and routed to noise",
            social_media_id=str(cast(UUID, raw_record.id)),
            noise_signal_id=str(noise_signal_id),
            confidence=confidence,
            platform=data.source_platform,
        )

        return SocialMediaIngestResult(
            ingestion_id=cast(UUID, raw_record.id),
            noise_created=True,
            noise_signal_id=noise_signal_id,
            confidence=confidence,
            message="Routed to Noise Block for manual review. Social media signals are never auto-verified.",
        )

    async def list_pending(
        self,
        db: AsyncSession,
        source_platform: str | None = None,
        competitor_id: UUID | None = None,
    ) -> list[SocialMediaRaw]:
        stmt = (
            select(SocialMediaRaw)
            .join(NoiseSignal, SocialMediaRaw.noise_signal_id == NoiseSignal.id)
            .where(NoiseSignal.verification_status == NoiseVerificationStatus.PENDING)
            .options(
                selectinload(SocialMediaRaw.molecule),
                selectinload(SocialMediaRaw.competitor),
                selectinload(SocialMediaRaw.noise_signal),
            )
        )
        if source_platform:
            stmt = stmt.where(SocialMediaRaw.source_platform == source_platform.upper())
        if competitor_id:
            stmt = stmt.where(SocialMediaRaw.competitor_id == competitor_id)
        stmt = stmt.order_by(SocialMediaRaw.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self, db: AsyncSession) -> dict[str, Any]:
        total_result = await db.execute(select(func.count(SocialMediaRaw.id)))
        total_ingested = total_result.scalar() or 0

        verified_result = await db.execute(
            select(func.count(SocialMediaRaw.id))
            .join(NoiseSignal, SocialMediaRaw.noise_signal_id == NoiseSignal.id)
            .where(NoiseSignal.verification_status == NoiseVerificationStatus.VERIFIED)
        )
        total_verified = verified_result.scalar() or 0

        dismissed_result = await db.execute(
            select(func.count(SocialMediaRaw.id))
            .join(NoiseSignal, SocialMediaRaw.noise_signal_id == NoiseSignal.id)
            .where(NoiseSignal.verification_status == NoiseVerificationStatus.DISMISSED)
        )
        total_dismissed = dismissed_result.scalar() or 0

        expired_result = await db.execute(
            select(func.count(SocialMediaRaw.id))
            .join(NoiseSignal, SocialMediaRaw.noise_signal_id == NoiseSignal.id)
            .where(NoiseSignal.verification_status == NoiseVerificationStatus.EXPIRED)
        )
        total_expired = expired_result.scalar() or 0

        platform_result = await db.execute(
            select(SocialMediaRaw.source_platform, func.count(SocialMediaRaw.id))
            .group_by(SocialMediaRaw.source_platform)
        )
        by_platform = {row[0]: row[1] for row in platform_result.all()}

        return {
            "total_ingested": total_ingested,
            "total_verified": total_verified,
            "total_dismissed": total_dismissed,
            "total_expired": total_expired,
            "by_platform": by_platform,
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _build_molecule_map(self, db: AsyncSession) -> dict[str, UUID]:
        """Build keyword -> molecule_id map from DB."""
        result = await db.execute(select(Molecule))
        molecules = result.scalars().all()
        mapping: dict[str, UUID] = {}
        for mol in molecules:
            mid = cast(UUID, mol.id)
            name = cast(str | None, mol.molecule_name)
            brand = cast(str | None, mol.reference_brand)
            if name:
                mapping[name.lower()] = mid
            if brand:
                mapping[brand.lower()] = mid
            search_terms = cast(list[str] | None, mol.search_terms) or []
            for term in search_terms:
                if term:
                    mapping[term.lower()] = mid
        return mapping

    async def _build_competitor_map(self, db: AsyncSession) -> dict[str, UUID]:
        """Build keyword -> competitor_id map from DB."""
        result = await db.execute(select(Competitor))
        competitors = result.scalars().all()
        mapping: dict[str, UUID] = {}
        for comp in competitors:
            cid = cast(UUID, comp.id)
            name = cast(str | None, comp.canonical_name)
            asset = cast(str | None, comp.asset_code)
            parent = cast(str | None, comp.parent_company)
            if name:
                mapping[name.lower()] = cid
            if asset:
                mapping[asset.lower()] = cid
            if parent:
                mapping[parent.lower()] = cid
        return mapping
