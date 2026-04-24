from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class PatentCliff(Base):  # type: ignore[misc]
    __tablename__ = "patent_cliffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_id = Column(
        UUID(as_uuid=True), ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False
    )
    indication = Column(String(255), nullable=False)
    patent_type = Column(String(50), nullable=False)
    patent_number = Column(String(50))
    expiry_date = Column(Date, nullable=False)
    territory = Column(String(10), nullable=False, default="US")
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    updated_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy, onupdate=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="patent_cliffs")
