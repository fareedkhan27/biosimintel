"""add_predictive_intelligence_and_llm_cache

Revision ID: 167a8a771f1a
Revises: 57262dc9f349
Create Date: 2026-04-24 00:58:04.623263

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "167a8a771f1a"
down_revision: str | None = "57262dc9f349"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add patent_cliffs, intelligence_baselines, and llm_insight_cache tables."""
    # patent_cliffs
    op.create_table(
        "patent_cliffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("indication", sa.String(255), nullable=False),
        sa.Column("patent_type", sa.String(50), nullable=False),
        sa.Column("patent_number", sa.String(50)),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("territory", sa.String(10), nullable=False, server_default="US"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_patent_cliffs_molecule", "patent_cliffs", ["molecule_id"])
    op.create_index("idx_patent_cliffs_expiry", "patent_cliffs", ["expiry_date"])

    # intelligence_baselines
    op.create_table(
        "intelligence_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_type", sa.String(50), nullable=False),
        sa.Column("baseline_value", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_baselines_molecule_type", "intelligence_baselines", ["molecule_id", "baseline_type"])

    # llm_insight_cache
    op.create_table(
        "llm_insight_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("key_insights", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("recommended_actions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(8, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_llm_cache_molecule", "llm_insight_cache", ["molecule_id"])
    op.create_index("idx_llm_cache_key", "llm_insight_cache", ["cache_key"])


def downgrade() -> None:
    """Remove predictive intelligence tables."""
    op.drop_index("idx_llm_cache_key", table_name="llm_insight_cache")
    op.drop_index("idx_llm_cache_molecule", table_name="llm_insight_cache")
    op.drop_table("llm_insight_cache")

    op.drop_index("idx_baselines_molecule_type", table_name="intelligence_baselines")
    op.drop_table("intelligence_baselines")

    op.drop_index("idx_patent_cliffs_expiry", table_name="patent_cliffs")
    op.drop_index("idx_patent_cliffs_molecule", table_name="patent_cliffs")
    op.drop_table("patent_cliffs")
