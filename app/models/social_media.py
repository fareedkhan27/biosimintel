from __future__ import annotations

import enum
import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class SocialMediaPlatform(enum.StrEnum):
    TWITTER = "TWITTER"
    REDDIT = "REDDIT"


class SocialMediaRaw(Base):  # type: ignore[misc]
    __tablename__ = "social_media_raw"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_platform = Column(
        String(20),
        nullable=False,
        default=SocialMediaPlatform.TWITTER,
    )
    post_url = Column(Text, nullable=False)
    author = Column(Text, nullable=True)
    post_text = Column(Text, nullable=False)
    published_date = Column(Date, nullable=True)
    engagement_score = Column(Integer, nullable=True)
    matched_keywords = Column(Text, nullable=True)
    molecule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="SET NULL"),
        nullable=True,
    )
    competitor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id", ondelete="SET NULL"),
        nullable=True,
    )
    noise_signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("noise_signals.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule")
    competitor = relationship("Competitor")
    noise_signal = relationship("NoiseSignal")

    __table_args__ = (
        Index("ix_social_media_raw_source_platform_published_date", "source_platform", "published_date"),
        Index("ix_social_media_raw_noise_signal_id", "noise_signal_id"),
    )
