from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class EmailRole(enum.StrEnum):
    GM = "gm"
    COMMERCIAL = "commercial"
    MEDICAL = "medical"
    MARKET_ACCESS = "market_access"
    REGULATORY = "regulatory"
    FINANCE = "finance"
    STRATEGY_OPS = "strategy_ops"


class EmailRegionFilter(enum.StrEnum):
    ALL = "all"
    CEE_EU = "cee_eu"
    LATAM = "latam"
    MEA = "mea"


class EmailDepartmentFilter(enum.StrEnum):
    ALL = "all"
    COMMERCIAL = "commercial"
    MEDICAL = "medical"
    MARKET_ACCESS = "market_access"
    REGULATORY = "regulatory"
    FINANCE = "finance"


class EmailOperatingModelThreshold(enum.StrEnum):
    ALL = "all"
    OPM = "opm"
    LPM = "lpm"
    PASSIVE = "passive"


class EmailPreference(Base):  # type: ignore[misc]
    __tablename__ = "email_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email = Column(String(200), nullable=False, unique=True)
    user_name = Column(String(200), nullable=False)
    role = Column(SAEnum(EmailRole, name="email_role"), nullable=False)
    region_filter = Column(
        SAEnum(EmailRegionFilter, name="email_region_filter"), nullable=False
    )
    department_filter = Column(
        SAEnum(EmailDepartmentFilter, name="email_department_filter"), nullable=False
    )
    operating_model_threshold = Column(
        SAEnum(EmailOperatingModelThreshold, name="email_om_threshold"),
        nullable=False,
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now_sqlalchemy,
        onupdate=utc_now_sqlalchemy,
    )
