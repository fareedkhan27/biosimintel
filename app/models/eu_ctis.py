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


class EuCtisRawScrape(Base):  # type: ignore[misc]
    __tablename__ = "eu_ctis_raw_scrapes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scrape_date = Column(Date, nullable=False, unique=True)
    portal_url = Column(Text, nullable=False)
    search_query = Column(Text, nullable=False)
    total_results = Column(Integer, nullable=True)
    raw_html = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    entries = relationship(
        "EuCtisEntry",
        back_populates="raw_scrape",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_eu_ctis_raw_scrapes_scrape_date", "scrape_date"),
    )


class EuCtisEntry(Base):  # type: ignore[misc]
    __tablename__ = "eu_ctis_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_scrape_id = Column(
        UUID(as_uuid=True),
        ForeignKey("eu_ctis_raw_scrapes.id", ondelete="CASCADE"),
        nullable=False,
    )
    ctis_number = Column(Text, nullable=False)
    sponsor_name = Column(Text, nullable=True)
    trial_title = Column(Text, nullable=False)
    intervention = Column(Text, nullable=True)
    condition = Column(Text, nullable=True)
    phase = Column(Text, nullable=True)
    status = Column(Text, nullable=True)
    eu_member_state = Column(Text, nullable=True)
    decision_date = Column(Date, nullable=True)
    ctis_url = Column(Text, nullable=False)
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

    raw_scrape = relationship("EuCtisRawScrape", back_populates="entries")
    molecule = relationship("Molecule")
    competitor = relationship("Competitor")

    __table_args__ = (
        Index("ix_eu_ctis_entries_ctis_number_decision_date", "ctis_number", "decision_date"),
        Index("ix_eu_ctis_entries_eu_member_state", "eu_member_state"),
    )
