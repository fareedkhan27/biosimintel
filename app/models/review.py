from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class Review(Base):  # type: ignore[misc]
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    reviewer_id = Column(String(100), nullable=False)
    review_status = Column(String(20), nullable=False)
    comments = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    event = relationship("Event")
