"""add_uspto_patentsview_polls

Revision ID: 3899bbde8883
Revises: 35891142a96b
Create Date: 2026-04-26 12:42:38.400795

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3899bbde8883'
down_revision: str | None = '35891142a96b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new enum value to signal_type
    op.execute("ALTER TYPE signal_type ADD VALUE 'PATENT_FILING'")

    op.create_table('uspto_raw_polls',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('poll_date', sa.Date(), nullable=False),
        sa.Column('search_query', sa.Text(), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('poll_date')
    )
    op.create_index('ix_uspto_raw_polls_poll_date', 'uspto_raw_polls', ['poll_date'], unique=False)

    op.create_table('uspto_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_poll_id', sa.UUID(), nullable=False),
        sa.Column('patent_number', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('assignee', sa.Text(), nullable=True),
        sa.Column('inventors', sa.Text(), nullable=True),
        sa.Column('filing_date', sa.Date(), nullable=True),
        sa.Column('grant_date', sa.Date(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('patent_url', sa.Text(), nullable=False),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('patent_type', sa.String(length=30), nullable=False),
        sa.Column('is_relevant', sa.Boolean(), nullable=False),
        sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_poll_id'], ['uspto_raw_polls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_uspto_entries_patent_number_grant_date', 'uspto_entries', ['patent_number', 'grant_date'], unique=False)
    op.create_index('ix_uspto_entries_patent_type', 'uspto_entries', ['patent_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_uspto_entries_patent_type', table_name='uspto_entries')
    op.drop_index('ix_uspto_entries_patent_number_grant_date', table_name='uspto_entries')
    op.drop_table('uspto_entries')
    op.drop_index('ix_uspto_raw_polls_poll_date', table_name='uspto_raw_polls')
    op.drop_table('uspto_raw_polls')
    # NOTE: PostgreSQL does not support removing enum values directly.
    # The PATENT_FILING enum value remains in signal_type until the type is rebuilt.
