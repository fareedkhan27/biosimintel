from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.dates import utc_now_sqlalchemy


class ComboCapability(enum.StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class MoleculePair(Base):  # type: ignore[misc]
    __tablename__ = "molecule_pairs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    primary_molecule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
    )
    secondary_molecule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
    )
    combo_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    primary_molecule = relationship("Molecule", foreign_keys=[primary_molecule_id])
    secondary_molecule = relationship("Molecule", foreign_keys=[secondary_molecule_id])


class CompetitorMoleculeAssignment(Base):  # type: ignore[misc]
    __tablename__ = "competitor_molecule_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("competitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    molecule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("molecules.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_name = Column(String(100), nullable=False)
    development_stage = Column(String(50), nullable=True)
    is_primary_focus = Column(Boolean, default=False)
    combo_capability = Column(
        SAEnum(ComboCapability, name="combo_capability"),
        nullable=False,
    )
    has_clinical_trial_for_combo = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now_sqlalchemy)

    competitor = relationship("Competitor")
    molecule = relationship("Molecule")

    __table_args__ = (
        UniqueConstraint(
            "competitor_id",
            "molecule_id",
            name="uq_competitor_molecule",
        ),
    )
