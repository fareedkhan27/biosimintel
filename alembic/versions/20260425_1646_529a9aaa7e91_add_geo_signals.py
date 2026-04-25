"""add_geo_signals

Revision ID: 529a9aaa7e91
Revises: c6362beb3933
Create Date: 2026-04-25 16:46:16.702293

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '529a9aaa7e91'
down_revision: str | None = 'c6362beb3933'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('geo_signals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=True),
    sa.Column('competitor_id', sa.UUID(), nullable=True),
    sa.Column('molecule_id', sa.UUID(), nullable=False),
    sa.Column('region_id', sa.UUID(), nullable=True),
    sa.Column('country_ids', postgresql.ARRAY(sa.UUID()), nullable=True),
    sa.Column('signal_type', sa.Enum('TRIAL_UPDATE', 'APPROVAL', 'PATENT', 'SEC_FILING', 'PRESS', 'PRICING', 'COMBO', name='signal_type'), nullable=False),
    sa.Column('confidence', sa.Enum('CONFIRMED', 'PROBABLE', 'UNCONFIRMED', name='confidence'), nullable=False),
    sa.Column('relevance_score', sa.Integer(), nullable=True),
    sa.Column('department_tags', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('operating_model_relevance', sa.Enum('OPM', 'LPM', 'PASSIVE', 'ALL', name='operating_model_relevance'), nullable=False),
    sa.Column('delta_note', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('source_type', sa.Text(), nullable=True),
    sa.Column('tier', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('tier BETWEEN 1 AND 3', name='check_signal_tier_range'),
    sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('geo_signals')
