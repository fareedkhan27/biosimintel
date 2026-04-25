from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class RegionCode(enum.StrEnum):
    CEE_EU = "CEE_EU"
    LATAM = "LATAM"
    MEA = "MEA"


class OperatingModel(enum.StrEnum):
    LPM = "LPM"
    OPM = "OPM"
    Passive = "Passive"


class Region(Base):  # type: ignore[misc]
    __tablename__ = "regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(SAEnum(RegionCode, name="region_code"), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    countries = relationship("Country", back_populates="region")
    capabilities = relationship("CompetitorCapability", back_populates="region")


class Country(Base):  # type: ignore[misc]
    __tablename__ = "countries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(String(2), nullable=False, unique=True)
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
    )
    operating_model = Column(SAEnum(OperatingModel, name="operating_model"), nullable=False)
    local_regulatory_agency_name = Column(String(100), nullable=True)
    local_currency_code = Column(String(3), nullable=True)
    ema_parallel_recognition = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    region = relationship("Region", back_populates="countries")


class CompetitorCapability(Base):  # type: ignore[misc]
    __tablename__ = "competitor_capabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
    )
    has_local_manufacturing = Column(Boolean, default=False)
    has_local_regulatory_filing = Column(Boolean, default=False)
    has_local_commercial_infrastructure = Column(Boolean, default=False)
    local_partner_name = Column(String(100), nullable=True)
    confidence_score = Column(Integer, default=0)
    assessed_at = Column(DateTime(timezone=True), nullable=True)
    source_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    competitor = relationship("Competitor")
    region = relationship("Region", back_populates="capabilities")
