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


class EpoRawPoll(Base):  # type: ignore[misc]
    __tablename__ = "epo_raw_polls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_date = Column(Date, nullable=False, unique=True)
    search_query = Column(Text, nullable=False)
    total_count = Column(Integer, nullable=True)
    raw_xml = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "EpoEntry",
        back_populates="raw_poll",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_epo_raw_polls_poll_date", "poll_date"),
    )


class EpoEntry(Base):  # type: ignore[misc]
    __tablename__ = "epo_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_poll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("epo_raw_polls.id", ondelete="CASCADE"),
        nullable=False,
    )
    epo_publication_number = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    applicant = Column(Text, nullable=True)
    inventors = Column(Text, nullable=True)
    filing_date = Column(Date, nullable=True)
    publication_date = Column(Date, nullable=True)
    patent_status = Column(Text, nullable=True)
    epo_url = Column(Text, nullable=False)
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
    patent_type = Column(String(30), nullable=False, default="GENERAL")
    is_relevant = Column(Boolean, default=False, nullable=False)
    signals_created_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    raw_poll = relationship("EpoRawPoll", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_epo_entries_epo_publication_number_publication_date", "epo_publication_number", "publication_date"),
        Index("ix_epo_entries_patent_type", "patent_type"),
    )
