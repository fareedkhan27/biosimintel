"""add_briefing_preferences_to_molecules

Revision ID: 4e3aed1cc707
Revises: 4b0461de3bb0
Create Date: 2026-04-24 21:05:36.109709

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4e3aed1cc707'
down_revision: str | None = '4b0461de3bb0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add briefing preference columns to molecules
    op.add_column(
        'molecules',
        sa.Column(
            'briefing_mode',
            sa.String(length=20),
            nullable=False,
            server_default='weekly_digest',
        ),
    )
    op.add_column(
        'molecules',
        sa.Column(
            'alert_threshold',
            sa.Integer(),
            nullable=False,
            server_default='60',
        ),
    )
    op.add_column(
        'molecules',
        sa.Column(
            'is_monitored',
            sa.Boolean(),
            nullable=False,
            server_default='true',
        ),
    )
    op.add_column(
        'molecules',
        sa.Column(
            'last_briefing_sent_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Add CHECK constraint for valid briefing_mode values
    op.create_check_constraint(
        'ck_molecules_briefing_mode',
        'molecules',
        sa.text("briefing_mode IN ('silent', 'alert_only', 'weekly_digest', 'on_demand')"),
    )


def downgrade() -> None:
    op.drop_constraint('ck_molecules_briefing_mode', 'molecules', type_='check')
    op.drop_column('molecules', 'last_briefing_sent_at')
    op.drop_column('molecules', 'is_monitored')
    op.drop_column('molecules', 'alert_threshold')
    op.drop_column('molecules', 'briefing_mode')
