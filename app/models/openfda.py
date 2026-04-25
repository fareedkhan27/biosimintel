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


class OpenfdaRawPoll(Base):  # type: ignore[misc]
    __tablename__ = "openfda_raw_polls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_date = Column(Date, nullable=False, unique=True)
    endpoint_url = Column(Text, nullable=False)
    query_params = Column(JSON, nullable=True)
    raw_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "OpenfdaEntry",
        back_populates="raw_poll",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_openfda_raw_polls_poll_date", "poll_date"),
    )


class OpenfdaEntry(Base):  # type: ignore[misc]
    __tablename__ = "openfda_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_poll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("openfda_raw_polls.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_number = Column(Text, nullable=True)
    brand_name = Column(Text, nullable=True)
    generic_name = Column(Text, nullable=True)
    manufacturer_name = Column(Text, nullable=True)
    product_type = Column(Text, nullable=True)
    submission_type = Column(Text, nullable=True)
    submission_status = Column(Text, nullable=True)
    approval_date = Column(Date, nullable=True)
    openfda_url = Column(Text, nullable=True)
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

    raw_poll = relationship("OpenfdaRawPoll", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_openfda_entries_application_number_approval_date", "application_number", "approval_date"),
        Index("ix_openfda_entries_generic_name_approval_date", "generic_name", "approval_date"),
    )
