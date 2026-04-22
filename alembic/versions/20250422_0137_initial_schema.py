"""Initial schema

Revision ID: 000000000001
Revises:
Create Date: 2025-04-22 01:37:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "000000000001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "molecules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("molecule_name", sa.String(100), nullable=False),
        sa.Column("reference_brand", sa.String(100), nullable=False),
        sa.Column("manufacturer", sa.String(100), nullable=False),
        sa.Column("search_terms", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("indications", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("loe_timeline", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("competitor_universe", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("scoring_weights", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("molecule_name"),
    )
    op.create_table(
        "scoring_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("version", sa.String(20), server_default="1.0", nullable=True),
        sa.Column("is_active", sa.String(20), server_default="active", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("asset_code", sa.String(50), nullable=True),
        sa.Column("development_stage", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), server_default="active", nullable=True),
        sa.Column("primary_markets", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("launch_window", sa.String(50), nullable=True),
        sa.Column("price_position", sa.String(100), nullable=True),
        sa.Column("parent_company", sa.String(100), nullable=True),
        sa.Column("partnership_status", sa.String(100), nullable=True),
        sa.Column("cik", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("molecule_id", "canonical_name"),
        sa.CheckConstraint("tier BETWEEN 1 AND 4", name="check_tier_range"),
    )
    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_name", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("processing_status", sa.String(20), server_default="pending", nullable=True),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("molecule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_subtype", sa.String(50), nullable=True),
        sa.Column("development_stage", sa.String(50), nullable=True),
        sa.Column("indication", sa.String(100), nullable=True),
        sa.Column("indication_priority", sa.String(10), nullable=True),
        sa.Column("is_pivotal_indication", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("extrapolation_targets", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("region", sa.String(50), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("announced_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("threat_score", sa.Integer(), nullable=True),
        sa.Column("traffic_light", sa.String(10), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("verification_status", sa.String(20), server_default="pending", nullable=True),
        sa.Column("verification_confidence", sa.Numeric(3, 2), server_default=sa.text("0.0"), nullable=True),
        sa.Column("verified_sources_count", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("review_status", sa.String(20), server_default="pending", nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_why_it_matters", sa.Text(), nullable=True),
        sa.Column("ai_recommended_action", sa.Text(), nullable=True),
        sa.Column("ai_confidence_note", sa.Text(), nullable=True),
        sa.Column("ai_interpreted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("threat_score BETWEEN 0 AND 100", name="check_threat_score_range"),
        sa.CheckConstraint("indication_priority IN ('HIGH', 'MEDIUM', 'LOW')", name="check_indication_priority"),
        sa.CheckConstraint("traffic_light IN ('Green', 'Amber', 'Red')", name="check_traffic_light"),
    )
    op.create_table(
        "data_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(50), nullable=False),
        sa.Column("extractor_version", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), server_default=sa.text("1.0"), nullable=True),
        sa.Column("verified_by", sa.String(50), nullable=True),
        sa.Column("verification_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", sa.String(100), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("data_provenance")
    op.drop_table("events")
    op.drop_table("source_documents")
    op.drop_table("competitors")
    op.drop_table("scoring_rules")
    op.drop_table("molecules")
