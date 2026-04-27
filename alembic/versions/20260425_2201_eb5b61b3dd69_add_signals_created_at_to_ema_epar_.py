"""add_signals_created_at_to_ema_epar_entries

Revision ID: eb5b61b3dd69
Revises: 19862056e634
Create Date: 2026-04-25 22:01:39.302019

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'eb5b61b3dd69'
down_revision: str | None = '19862056e634'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('ema_epar_entries', sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('ema_epar_entries', 'signals_created_at')
