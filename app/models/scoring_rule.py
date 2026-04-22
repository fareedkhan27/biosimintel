from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class ScoringRule(Base):  # type: ignore[misc]
    __tablename__ = "scoring_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)
    description = Column(Text)
    config = Column(JSON, default=dict)
    version = Column(String(20), default="1.0")
    is_active = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
