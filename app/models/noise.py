from __future__ import annotations

import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class NoiseSourceType(enum.StrEnum):
    PRESS = "press"
    SOCIAL = "social"
    CONFERENCE = "conference"
    ANALYST = "analyst"
    RUMOR = "rumor"


class NoiseVerificationStatus(enum.StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class NoiseSignal(Base):  # type: ignore[misc]
    __tablename__ = "noise_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    geo_signal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geo_signals.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_text = Column(Text, nullable=False)
    source_type = Column(SAEnum(NoiseSourceType, name="noise_source_type"), nullable=False)
    source_url = Column(Text, nullable=True)
    source_author = Column(String(100), nullable=True)
    flagged_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    verification_status = Column(
        SAEnum(NoiseVerificationStatus, name="noise_verification_status"),
        nullable=False,
        default=NoiseVerificationStatus.PENDING,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_by = Column(String(100), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    verification_notes = Column(Text, nullable=True)
    escalation_count = Column(Integer, default=0)
