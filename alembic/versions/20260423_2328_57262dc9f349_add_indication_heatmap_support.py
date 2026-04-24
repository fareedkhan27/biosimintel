"""add_indication_heatmap_support

Revision ID: 57262dc9f349
Revises: 05a2f3098ad4
Create Date: 2026-04-23 23:28:43.937179

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57262dc9f349"
down_revision: str | None = "05a2f3098ad4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes to support fast indication heatmap queries."""
    # Index for fast filtering by indication
    op.create_index(
        "idx_events_indication",
        "events",
        ["indication"],
        postgresql_where="indication IS NOT NULL",
    )
    # Composite index for heatmap matrix queries
    op.create_index(
        "idx_events_molecule_indication_competitor",
        "events",
        ["molecule_id", "indication", "competitor_id"],
        postgresql_where="indication IS NOT NULL",
    )


def downgrade() -> None:
    """Remove indication heatmap indexes."""
    op.drop_index("idx_events_molecule_indication_competitor", table_name="events")
    op.drop_index("idx_events_indication", table_name="events")
