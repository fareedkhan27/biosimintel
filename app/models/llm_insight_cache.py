from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class LlmInsightCache(Base):  # type: ignore[misc]
    __tablename__ = "llm_insight_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    molecule_id = Column(
        UUID(as_uuid=True), ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False
    )
    cache_key = Column(String(128), nullable=False, unique=True)
    context_hash = Column(String(64), nullable=False)
    executive_summary = Column(Text, nullable=False)
    key_insights = Column(JSONB, nullable=False, default=list)
    recommended_actions = Column(JSONB, nullable=False, default=list)
    model_used = Column(String(100), nullable=False)
    tokens_input = Column(Integer, nullable=False)
    tokens_output = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(8, 6), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    molecule = relationship("Molecule", back_populates="llm_insight_caches")
