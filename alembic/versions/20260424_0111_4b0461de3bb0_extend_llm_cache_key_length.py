"""extend_llm_cache_key_length

Revision ID: 4b0461de3bb0
Revises: 167a8a771f1a
Create Date: 2026-04-24 01:11:27.454413

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b0461de3bb0"
down_revision: str | None = "167a8a771f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend llm_insight_cache.cache_key from 64 to 128 characters."""
    op.alter_column(
        "llm_insight_cache",
        "cache_key",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert llm_insight_cache.cache_key to 64 characters."""
    op.alter_column(
        "llm_insight_cache",
        "cache_key",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
