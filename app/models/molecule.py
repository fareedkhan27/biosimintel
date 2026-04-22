from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, String
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

    competitors = relationship("Competitor", back_populates="molecule", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="molecule")
    source_documents = relationship("SourceDocument", back_populates="molecule")
