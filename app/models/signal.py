from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class SignalType(enum.StrEnum):
    TRIAL_UPDATE = "trial_update"
    APPROVAL = "approval"
    PATENT = "patent"
    SEC_FILING = "sec_filing"
    PRESS = "press"
    PRICING = "pricing"
    COMBO = "combo"
    EMA_EPAR_APPROVAL = "ema_epar_approval"
    FDA_BIOSIMILAR_APPROVAL = "fda_biosimilar_approval"
    FDA_LABEL_UPDATE = "fda_label_update"
    FDA_PENDING_APPROVAL = "fda_pending_approval"
    PUBLICATION_PHASE3 = "publication_phase3"
    PUBLICATION_SAFETY = "publication_safety"
    PUBLICATION_RWE = "publication_rwe"
    PUBLICATION_GENERAL = "publication_general"
    PATENT_FILING = "patent_filing"
    EP_PATENT = "EP_PATENT"
    PRESS_RELEASE = "PRESS_RELEASE"


class Confidence(enum.StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    UNCONFIRMED = "unconfirmed"


class OperatingModelRelevance(enum.StrEnum):
    OPM = "opm"
    LPM = "lpm"
    PASSIVE = "passive"
    ALL = "all"


class GeoSignal(Base):  # type: ignore[misc]
    __tablename__ = "geo_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=True,
    )
    competitor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id", ondelete="CASCADE"),
        nullable=True,
    )
    molecule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    country_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    signal_type = Column(SAEnum(SignalType, name="signal_type"), nullable=False)
    confidence = Column(SAEnum(Confidence, name="confidence"), nullable=False)
    relevance_score = Column(Integer, default=0)
    department_tags = Column(ARRAY(Text), nullable=True)
    operating_model_relevance = Column(
        SAEnum(OperatingModelRelevance, name="operating_model_relevance"),
        nullable=False,
    )
    delta_note = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    source_type = Column(Text, nullable=True)
    tier = Column(Integer, default=3)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now_sqlalchemy,
        onupdate=utc_now_sqlalchemy,
    )

    event = relationship("Event")
    competitor = relationship("Competitor")
    molecule = relationship("Molecule")
    region = relationship("Region")

    __table_args__ = (
        CheckConstraint("tier BETWEEN 1 AND 3", name="check_signal_tier_range"),
    )
