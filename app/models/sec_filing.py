from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class SecFiling(Base):  # type: ignore[misc]
    __tablename__ = "sec_filings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id"),
        nullable=False,
        index=True,
    )
    cik = Column(String(20), nullable=False, index=True)
    form_type = Column(String(10), nullable=False)  # 10-K, 10-Q, 8-K
    filing_date = Column(DateTime, nullable=False)
    accession_number = Column(String(50), nullable=False, unique=True)
    primary_doc_url = Column(String(500), nullable=False)
    title = Column(String(500), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
