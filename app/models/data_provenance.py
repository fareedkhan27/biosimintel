from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class DataProvenance(Base):  # type: ignore[misc]
    __tablename__ = "data_provenance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    raw_value = Column(Text)
    normalized_value = Column(Text)
    extraction_method = Column(String(50), nullable=False)
    extractor_version = Column(String(20))
    confidence = Column(Numeric(3, 2), default=1.0)
    verified_by = Column(String(50))
    verification_timestamp = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    event = relationship("Event", back_populates="provenance")
    source_document = relationship("SourceDocument", back_populates="provenance_records")
