from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class Molecule(Base):  # type: ignore[misc]
    __tablename__ = "molecules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_name = Column(String(100), unique=True, nullable=False)
    reference_brand = Column(String(100), nullable=False)
    manufacturer = Column(String(100), nullable=False)
    search_terms = Column(JSON, default=list)
    indications = Column(JSON, default=dict)
    loe_timeline = Column(JSON, default=dict)
    competitor_universe = Column(JSON, default=list)
    scoring_weights = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    # Phase 2: expanded molecule metadata
    inn = Column(String(100), unique=True, nullable=True)
    brand_name = Column(String(100), nullable=True)
    mechanism_of_action = Column(String(200), nullable=True)
    therapeutic_area = Column(String(100), nullable=True)
    status = Column(String(20), nullable=True, default="active")
    is_reference_product = Column(Boolean, default=False)

    # Briefing preference controls (Phase 4D)
    briefing_mode = Column(String(20), nullable=False, default="weekly_digest")
    alert_threshold = Column(Integer, nullable=False, default=60)
    is_monitored = Column(Boolean, nullable=False, default=True)
    last_briefing_sent_at = Column(DateTime(timezone=True), nullable=True)

    competitors = relationship("Competitor", back_populates="molecule", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="molecule")
    source_documents = relationship("SourceDocument", back_populates="molecule")
    patent_cliffs = relationship("PatentCliff", back_populates="molecule", cascade="all, delete-orphan")
    intelligence_baselines = relationship("IntelligenceBaseline", back_populates="molecule", cascade="all, delete-orphan")
    llm_insight_caches = relationship("LlmInsightCache", back_populates="molecule", cascade="all, delete-orphan")

    @property
    def should_send_weekly_digest(self) -> bool:
        return self.briefing_mode == "weekly_digest" and self.is_monitored
