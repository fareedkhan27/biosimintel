from __future__ import annotations

import uuid

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class Competitor(Base):  # type: ignore[misc]
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_id = Column(UUID(as_uuid=True), ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False)
    canonical_name = Column(String(100), nullable=False)
    tier = Column(Integer, nullable=False)
    asset_code = Column(String(50))
    development_stage = Column(String(50))
    status = Column(String(50), default="active")
    primary_markets = Column(JSON, default=list)
    launch_window = Column(String(50))
    price_position = Column(String(100))
    parent_company = Column(String(100))
    partnership_status = Column(String(100))
    cik = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="competitors")
    events = relationship("Event", back_populates="competitor")

    __table_args__ = (
        CheckConstraint("tier BETWEEN 1 AND 4", name="check_tier_range"),
    )
