from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class IntelligenceBaseline(Base):  # type: ignore[misc]
    __tablename__ = "intelligence_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_id = Column(
        UUID(as_uuid=True), ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False
    )
    baseline_type = Column(String(50), nullable=False)
    baseline_value = Column(Integer, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="intelligence_baselines")
