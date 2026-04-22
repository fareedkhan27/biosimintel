from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class Event(Base):  # type: ignore[misc]
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_id = Column(UUID(as_uuid=True), ForeignKey("molecules.id"), nullable=False)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id"))
    event_type = Column(String(50), nullable=False)
    event_subtype = Column(String(50))
    development_stage = Column(String(50))
    indication = Column(String(100))
    indication_priority = Column(String(10), CheckConstraint("indication_priority IN ('HIGH', 'MEDIUM', 'LOW')"))
    is_pivotal_indication = Column(Boolean, default=False)
    extrapolation_targets = Column(JSON, default=list)
    country = Column(String(100))
    region = Column(String(50))
    event_date = Column(DateTime(timezone=True))
    announced_date = Column(DateTime(timezone=True))
    summary = Column(Text)
    evidence_excerpt = Column(Text)
    threat_score = Column(Integer, CheckConstraint("threat_score BETWEEN 0 AND 100"))
    traffic_light = Column(String(10), CheckConstraint("traffic_light IN ('Green', 'Amber', 'Red')"))
    score_breakdown = Column(JSON)
    verification_status = Column(String(20), default="pending")
    verification_confidence = Column(Numeric(3, 2), default=0.0)
    verified_sources_count = Column(Integer, default=0)
    review_status = Column(String(20), default="pending")
    ai_summary = Column(Text)
    ai_why_it_matters = Column(Text)
    ai_recommended_action = Column(Text)
    ai_confidence_note = Column(Text)
    ai_interpreted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    updated_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy, onupdate=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="events")
    source_document = relationship("SourceDocument", back_populates="events")
    competitor = relationship("Competitor", back_populates="events")
    provenance = relationship("DataProvenance", back_populates="event", cascade="all, delete-orphan")
