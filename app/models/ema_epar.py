from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class EmaEparRawPoll(Base):  # type: ignore[misc]
    __tablename__ = "ema_epar_raw_polls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_date = Column(Date, nullable=False, unique=True)
    endpoint_url = Column(Text, nullable=False)
    raw_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "EmaEparEntry",
        back_populates="raw_poll",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_ema_epar_raw_polls_poll_date", "poll_date"),
    )


class EmaEparEntry(Base):  # type: ignore[misc]
    __tablename__ = "ema_epar_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_poll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ema_epar_raw_polls.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_name = Column(Text, nullable=False)
    active_substance = Column(Text, nullable=False)
    marketing_authorisation_holder = Column(Text, nullable=False)
    authorisation_status = Column(Text, nullable=False)
    indication = Column(Text, nullable=True)
    decision_date = Column(Date, nullable=True)
    epar_url = Column(Text, nullable=False)
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

    raw_poll = relationship("EmaEparRawPoll", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_ema_epar_entries_active_substance_decision_date", "active_substance", "decision_date"),
    )
