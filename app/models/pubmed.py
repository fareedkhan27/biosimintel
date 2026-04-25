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
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class PubmedRawPoll(Base):  # type: ignore[misc]
    __tablename__ = "pubmed_raw_polls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_date = Column(Date, nullable=False, unique=True)
    search_query = Column(Text, nullable=False)
    total_count = Column(Integer, nullable=True)
    raw_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "PubmedEntry",
        back_populates="raw_poll",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_pubmed_raw_polls_poll_date", "poll_date"),
    )


class PubmedEntry(Base):  # type: ignore[misc]
    __tablename__ = "pubmed_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_poll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pubmed_raw_polls.id", ondelete="CASCADE"),
        nullable=False,
    )
    pmid = Column(Text, nullable=False)
    doi = Column(Text, nullable=True)
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)
    journal = Column(Text, nullable=True)
    pub_date = Column(Date, nullable=True)
    article_url = Column(Text, nullable=False)
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
    publication_type = Column(String(30), nullable=False, default="GENERAL")
    is_relevant = Column(Boolean, default=False, nullable=False)
    signals_created_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    raw_poll = relationship("PubmedRawPoll", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_pubmed_entries_pmid_pub_date", "pmid", "pub_date"),
        Index("ix_pubmed_entries_publication_type", "publication_type"),
    )
