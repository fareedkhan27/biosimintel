"""add_noise_signals

Revision ID: 2393ab056ab4
Revises: 61f57e3f1c04
Create Date: 2026-04-25 17:31:17.206508

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2393ab056ab4'
down_revision: str | None = '61f57e3f1c04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('noise_signals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('geo_signal_id', sa.UUID(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('source_type', sa.Enum('PRESS', 'SOCIAL', 'CONFERENCE', 'ANALYST', 'RUMOR', name='noise_source_type'), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('source_author', sa.String(length=100), nullable=True),
    sa.Column('flagged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification_status', sa.Enum('PENDING', 'VERIFIED', 'DISMISSED', 'EXPIRED', name='noise_verification_status'), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.String(length=100), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dismissed_by', sa.String(length=100), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification_notes', sa.Text(), nullable=True),
    sa.Column('escalation_count', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['geo_signal_id'], ['geo_signals.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('noise_signals')
