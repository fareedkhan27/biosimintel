"""add_email_preferences

Revision ID: 61f57e3f1c04
Revises: 529a9aaa7e91
Create Date: 2026-04-25 17:17:58.493385

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '61f57e3f1c04'
down_revision: str | None = '529a9aaa7e91'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('email_preferences',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_email', sa.String(length=200), nullable=False),
    sa.Column('user_name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.Enum('GM', 'COMMERCIAL', 'MEDICAL', 'MARKET_ACCESS', 'REGULATORY', 'FINANCE', 'STRATEGY_OPS', name='email_role'), nullable=False),
    sa.Column('region_filter', sa.Enum('ALL', 'CEE_EU', 'LATAM', 'MEA', name='email_region_filter'), nullable=False),
    sa.Column('department_filter', sa.Enum('ALL', 'COMMERCIAL', 'MEDICAL', 'MARKET_ACCESS', 'REGULATORY', 'FINANCE', name='email_department_filter'), nullable=False),
    sa.Column('operating_model_threshold', sa.Enum('ALL', 'OPM', 'LPM', 'PASSIVE', name='email_om_threshold'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_email')
    )


def downgrade() -> None:
    op.drop_table('email_preferences')
