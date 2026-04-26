from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class WhoIctrpRawPoll(Base):  # type: ignore[misc]
    __tablename__ = "who_ictrp_raw_polls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_month = Column(Text, nullable=False, unique=True)
    download_url = Column(Text, nullable=False)
    csv_filename = Column(Text, nullable=True)
    total_rows = Column(Integer, nullable=True)
    filtered_rows = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "WhoIctrpEntry",
        back_populates="raw_poll",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_who_ictrp_raw_polls_poll_month", "poll_month"),
    )


class WhoIctrpEntry(Base):  # type: ignore[misc]
    __tablename__ = "who_ictrp_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_poll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("who_ictrp_raw_polls.id", ondelete="CASCADE"),
        nullable=False,
    )
    trial_id = Column(Text, nullable=False)
    reg_id = Column(Text, nullable=True)
    public_title = Column(Text, nullable=False)
    scientific_title = Column(Text, nullable=True)
    intervention = Column(Text, nullable=True)
    condition = Column(Text, nullable=True)
    recruitment_status = Column(Text, nullable=True)
    phase = Column(Text, nullable=True)
    study_type = Column(Text, nullable=True)
    date_registration = Column(Date, nullable=True)
    date_enrolment = Column(Date, nullable=True)
    countries = Column(Text, nullable=True)
    source_register = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
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
    is_relevant = Column(Boolean, default=False, nullable=False)
    signals_created_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    raw_poll = relationship("WhoIctrpRawPoll", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_who_ictrp_entries_trial_id_date_registration", "trial_id", "date_registration"),
        Index("ix_who_ictrp_entries_source_register", "source_register"),
    )
