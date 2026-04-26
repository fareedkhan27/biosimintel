from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.models.competitor import Competitor
from app.models.geo import CompetitorCapability, Country
from app.models.molecule import Molecule
from app.models.noise import NoiseSignal, NoiseSourceType, NoiseVerificationStatus
from app.models.press_release import PressReleaseRaw, PressReleaseStatus
from app.models.signal import Confidence, GeoSignal, OperatingModelRelevance, SignalType
from app.schemas.press_release import PressReleaseIngestResult, PressReleaseRawCreate

logger = get_logger(__name__)


class PressReleaseService:
    """Ingest press releases, auto-classify, and route to GeoSignal or NoiseSignal."""

    async def ingest_press_release(
        self,
        data: PressReleaseRawCreate,
        db: AsyncSession,
    ) -> PressReleaseIngestResult:
        # Step 1 — Build keyword maps dynamically from DB
        molecule_map = await self._build_molecule_map(db)
        competitor_map = await self._build_competitor_map(db)

        combined = (data.article_title + " " + (data.article_summary or "")).lower()

        # Match molecule
        molecule_id: UUID | None = None
        for kw, mid in molecule_map.items():
            if kw in combined:
                molecule_id = mid
                break

        # Match competitor
        competitor_id: UUID | None = None
        for kw, cid in competitor_map.items():
            if kw in combined:
                competitor_id = cid
                break

        # Classify signal type
        signal_type = self._classify_signal_type(combined)

        # Step 2 — Confidence scoring
        confidence = 60  # Base for press releases
        if molecule_id and competitor_id:
            confidence = 85
        elif competitor_id and signal_type in {"LAUNCH", "REGULATORY_FILING"}:
            confidence = 80
        elif competitor_id:
            confidence = 70

        # Step 3 — Routing
        auto_verified = False
        status = PressReleaseStatus.PENDING
        signal_created = False
        noise_created = False
        signal_id: UUID | None = None

        geo_signal_threshold = getattr(settings, "PRESS_RELEASE_AUTO_VERIFY_THRESHOLD", 80)

        if (
            confidence >= geo_signal_threshold
            and signal_type in {"LAUNCH", "REGULATORY_FILING", "PARTNERSHIP"}
            and molecule_id is not None
        ):
            status = PressReleaseStatus.VERIFIED
            auto_verified = True
            geo_signal = await self._create_geo_signal(
                db, data, molecule_id, competitor_id, signal_type, confidence
            )
            signal_id = cast(UUID, geo_signal.id)
            signal_created = True
            logger.info(
                "Press release auto-verified and signal created",
                signal_id=str(signal_id),
                confidence=confidence,
                classification=signal_type,
            )
        else:
            status = PressReleaseStatus.PENDING
            noise = await self._create_noise_signal(
                db, data, molecule_id, competitor_id, signal_type, confidence
            )
            noise_created = True
            logger.info(
                "Press release routed to noise",
                noise_id=str(cast(UUID, noise.id)),
                confidence=confidence,
                classification=signal_type,
            )

        # Store the raw record
        raw_record = PressReleaseRaw(
            source_name=data.source_name,
            source_url=data.source_url,
            feed_type=data.feed_type,
            article_title=data.article_title,
            article_summary=data.article_summary,
            article_content=data.article_content,
            published_date=data.published_date,
            author=data.author,
            status=status,
            molecule_id=molecule_id,
            competitor_id=competitor_id,
            signal_type=signal_type,
            auto_verified=auto_verified,
        )
        db.add(raw_record)
        await db.commit()
        await db.refresh(raw_record)

        return PressReleaseIngestResult(
            ingestion_id=cast(UUID, raw_record.id),
            status=status.value,
            signal_created=signal_created,
            signal_id=signal_id,
            noise_created=noise_created,
            classification=signal_type,
            confidence=confidence,
        )

    async def verify_press_release(
        self,
        press_release_id: UUID,
        db: AsyncSession,
    ) -> GeoSignal:
        result = await db.execute(
            select(PressReleaseRaw).where(PressReleaseRaw.id == press_release_id)
        )
        pr = result.scalar_one_or_none()
        if pr is None:
            raise ValueError(f"PressReleaseRaw not found: {press_release_id}")

        if pr.status == PressReleaseStatus.VERIFIED:
            # Already verified — return existing signal if any
            signal_result = await db.execute(
                select(GeoSignal)
                .where(GeoSignal.source_url == pr.source_url)
                .order_by(GeoSignal.created_at.desc())
                .limit(1)
            )
            existing = signal_result.scalar_one_or_none()
            if existing:
                return existing

        pr.status = PressReleaseStatus.VERIFIED  # type: ignore[assignment]
        pr.auto_verified = False  # type: ignore[assignment]
        await db.flush()

        if pr.molecule_id is None:
            raise ValueError("Cannot verify press release without matched molecule")

        geo_signal = await self._create_geo_signal(
            db,
            PressReleaseRawCreate(
                source_name=cast(str, pr.source_name),
                source_url=cast(str, pr.source_url),
                feed_type=cast(str, pr.feed_type),
                article_title=cast(str, pr.article_title),
                article_summary=cast(str | None, pr.article_summary),
                article_content=cast(str | None, pr.article_content),
                published_date=cast(date | None, pr.published_date),
                author=cast(str | None, pr.author),
            ),
            cast(UUID, pr.molecule_id),
            cast(UUID | None, pr.competitor_id),
            cast(str, pr.signal_type) or "GENERAL",
            75,  # Manual verification confidence
        )
        await db.commit()
        await db.refresh(geo_signal)
        logger.info("Press release manually verified", press_release_id=str(press_release_id))
        return geo_signal

    async def dismiss_press_release(
        self,
        press_release_id: UUID,
        db: AsyncSession,
    ) -> PressReleaseRaw:
        result = await db.execute(
            select(PressReleaseRaw).where(PressReleaseRaw.id == press_release_id)
        )
        pr = result.scalar_one_or_none()
        if pr is None:
            raise ValueError(f"PressReleaseRaw not found: {press_release_id}")

        pr.status = PressReleaseStatus.DISMISSED  # type: ignore[assignment]
        await db.commit()
        await db.refresh(pr)
        logger.info("Press release dismissed", press_release_id=str(press_release_id))
        return pr

    async def list_pending(
        self,
        db: AsyncSession,
        competitor_id: UUID | None = None,
        source_name: str | None = None,
        signal_type: str | None = None,
    ) -> list[PressReleaseRaw]:
        stmt = (
            select(PressReleaseRaw)
            .where(PressReleaseRaw.status == PressReleaseStatus.PENDING)
            .options(selectinload(PressReleaseRaw.molecule), selectinload(PressReleaseRaw.competitor))
        )
        if competitor_id:
            stmt = stmt.where(PressReleaseRaw.competitor_id == competitor_id)
        if source_name:
            stmt = stmt.where(PressReleaseRaw.source_name.ilike(f"%{source_name}%"))
        if signal_type:
            stmt = stmt.where(PressReleaseRaw.signal_type == signal_type)
        stmt = stmt.order_by(PressReleaseRaw.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_verified(
        self,
        db: AsyncSession,
    ) -> list[PressReleaseRaw]:
        stmt = (
            select(PressReleaseRaw)
            .where(PressReleaseRaw.status == PressReleaseStatus.VERIFIED)
            .options(selectinload(PressReleaseRaw.molecule), selectinload(PressReleaseRaw.competitor))
            .order_by(PressReleaseRaw.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_press_release_signals(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[GeoSignal], int]:
        stmt = (
            select(GeoSignal)
            .where(GeoSignal.signal_type == SignalType.PRESS_RELEASE)
            .order_by(GeoSignal.created_at.desc())
        )
        count_result = await db.execute(select(stmt.subquery().c.id))
        total = len(count_result.all())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        signals = list(result.scalars().all())
        return signals, total

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

    def _classify_signal_type(self, combined: str) -> str:
        if any(
            x in combined
            for x in [
                "partnership",
                "collaboration",
                "agreement",
                "license",
                "distribution deal",
                "co-marketing",
            ]
        ):
            return "PARTNERSHIP"
        if any(
            x in combined
            for x in [
                "phase 3",
                "phase iii",
                "phase 2",
                "phase 1",
                "clinical trial",
                "pivotal",
                "readout",
                "data",
                "efficacy",
                "safety",
            ]
        ):
            return "PIPELINE_UPDATE"
        if any(
            x in combined
            for x in [
                "funding",
                "investment",
                "series",
                "venture",
                "capital",
                "financing",
            ]
        ):
            return "FUNDING"
        if any(
            x in combined
            for x in [
                "filed",
                "filing",
                "submitted",
                "application",
                "maa",
                "bla",
                "nda",
                "regulatory submission",
            ]
        ):
            return "REGULATORY_FILING"
        if any(
            x in combined
            for x in [
                "launch",
                "launched",
                "available",
                "market entry",
                "commercialization",
                "first sale",
            ]
        ):
            return "LAUNCH"
        return "GENERAL"

    async def _create_geo_signal(
        self,
        db: AsyncSession,
        data: PressReleaseRawCreate,
        molecule_id: UUID,
        competitor_id: UUID | None,
        signal_classification: str,
        confidence_score: int,
    ) -> GeoSignal:
        # Determine tier
        tier = 2 if signal_classification in {"LAUNCH", "REGULATORY_FILING"} else 3

        # Determine countries
        country_ids: list[UUID] = []
        if signal_classification in {"LAUNCH", "REGULATORY_FILING"}:
            all_countries_result = await db.execute(
                select(Country).where(Country.is_active.is_(True))
            )
            country_ids = [cast(UUID, c.id) for c in all_countries_result.scalars().all()]
        elif competitor_id is not None:
            cap_result = await db.execute(
                select(CompetitorCapability).where(
                    CompetitorCapability.competitor_id == competitor_id,
                    CompetitorCapability.confidence_score > 20,
                )
            )
            capabilities = cap_result.scalars().all()
            region_ids = [cap.region_id for cap in capabilities if cap.region_id]
            if region_ids:
                country_result = await db.execute(
                    select(Country).where(Country.region_id.in_(region_ids))
                )
                country_ids = [cast(UUID, c.id) for c in country_result.scalars().all()]

        if not country_ids:
            # Fallback to all active countries
            all_countries_result = await db.execute(
                select(Country).where(Country.is_active.is_(True))
            )
            country_ids = [cast(UUID, c.id) for c in all_countries_result.scalars().all()]

        # Build description
        comp_name = "Unknown"
        if competitor_id:
            comp_result = await db.execute(
                select(Competitor).where(Competitor.id == competitor_id)
            )
            comp = comp_result.scalar_one_or_none()
            if comp:
                comp_name = cast(str, comp.canonical_name)

        description = (
            f"{data.source_name}: {data.article_title}. "
            f"Competitor: {comp_name}. "
            f"Classification: {signal_classification}. "
            f"Published: {data.published_date or 'N/A'}"
        )

        expires_at: datetime | None = None
        if tier == 3:
            expires_at = datetime.now(UTC) + timedelta(days=7)

        confidence = (
            Confidence.CONFIRMED
            if tier == 1
            else Confidence.PROBABLE
            if tier == 2
            else Confidence.UNCONFIRMED
        )

        geo_signal = GeoSignal(
            event_id=None,
            competitor_id=competitor_id,
            molecule_id=molecule_id,
            region_id=None,
            country_ids=country_ids,
            signal_type=SignalType.PRESS_RELEASE,
            confidence=confidence,
            relevance_score=confidence_score,
            department_tags=["commercial", "medical"],
            operating_model_relevance=OperatingModelRelevance.ALL,
            delta_note=description,
            source_url=data.source_url,
            source_type="press_release",
            tier=tier,
            expires_at=expires_at,
        )
        db.add(geo_signal)
        await db.flush()
        await db.refresh(geo_signal)
        return geo_signal

    async def _create_noise_signal(
        self,
        db: AsyncSession,
        data: PressReleaseRawCreate,
        _molecule_id: UUID | None,
        competitor_id: UUID | None,
        _signal_classification: str,
        _confidence_score: int,
    ) -> NoiseSignal:
        # Try to link to most recent geo signal for same competitor
        geo_signal_id: UUID | None = None
        if competitor_id:
            signal_result = await db.execute(
                select(GeoSignal)
                .where(GeoSignal.competitor_id == competitor_id)
                .order_by(GeoSignal.created_at.desc())
                .limit(1)
            )
            gs = signal_result.scalar_one_or_none()
            if gs:
                geo_signal_id = cast(UUID, gs.id)

        expiry_days = getattr(settings, "PRESS_RELEASE_NOISE_EXPIRY_DAYS", 7)
        expires_at = datetime.now(UTC) + timedelta(days=expiry_days)

        raw_text = data.article_summary or data.article_title
        noise = NoiseSignal(
            geo_signal_id=geo_signal_id,
            raw_text=raw_text,
            source_type=NoiseSourceType.PRESS,
            source_url=data.source_url,
            source_author=data.author,
            flagged_at=datetime.now(UTC),
            verification_status=NoiseVerificationStatus.PENDING,
            expires_at=expires_at,
        )
        db.add(noise)
        await db.flush()
        await db.refresh(noise)
        return noise
