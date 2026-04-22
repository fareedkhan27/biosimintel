from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class SourceDocument(Base):  # type: ignore[misc]
    __tablename__ = "source_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String(50), nullable=False)
    source_type = Column(String(50), nullable=False)
    external_id = Column(String(200))
    title = Column(Text)
    url = Column(Text, nullable=False)
    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    raw_payload = Column(JSON)
    raw_text = Column(Text)
    content_hash = Column(String(64))
    processing_status = Column(String(20), default="pending")
    molecule_id = Column(UUID(as_uuid=True), ForeignKey("molecules.id"))
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="source_documents")
    events = relationship("Event", back_populates="source_document")
    provenance_records = relationship("DataProvenance", back_populates="source_document")
