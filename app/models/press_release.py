from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class FeedType(enum.StrEnum):
    RSS = "RSS"
    MANUAL = "MANUAL"
    WEBHOOK = "WEBHOOK"


class PressReleaseStatus(enum.StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    NOISE = "noise"
    DISMISSED = "dismissed"


class PressReleaseRaw(Base):  # type: ignore[misc]
    __tablename__ = "press_release_raw"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    feed_type = Column(Text, nullable=False, default=FeedType.MANUAL)
    article_title = Column(Text, nullable=False)
    article_summary = Column(Text, nullable=True)
    article_content = Column(Text, nullable=True)
    published_date = Column(Date, nullable=True)
    author = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default=PressReleaseStatus.PENDING)
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
    signal_type = Column(Text, nullable=True)
    auto_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_press_release_raw_source_name_published_date", "source_name", "published_date"),
        Index("ix_press_release_raw_status", "status"),
        Index("ix_press_release_raw_competitor_id", "competitor_id"),
    )
