"""add_press_release_ingestion

Revision ID: 0533ffe570f2
Revises: 1f46d2d80202
Create Date: 2026-04-26 13:51:58.539626

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0533ffe570f2'
down_revision: Union[str, None] = '1f46d2d80202'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE signal_type ADD VALUE 'press_release'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'PRESS_RELEASE'")

    op.create_table('press_release_raw',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_name', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('feed_type', sa.Text(), nullable=False),
        sa.Column('article_title', sa.Text(), nullable=False),
        sa.Column('article_summary', sa.Text(), nullable=True),
        sa.Column('article_content', sa.Text(), nullable=True),
        sa.Column('published_date', sa.Date(), nullable=True),
        sa.Column('author', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('signal_type', sa.Text(), nullable=True),
        sa.Column('auto_verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_press_release_raw_competitor_id', 'press_release_raw', ['competitor_id'], unique=False)
    op.create_index('ix_press_release_raw_source_name_published_date', 'press_release_raw', ['source_name', 'published_date'], unique=False)
    op.create_index('ix_press_release_raw_status', 'press_release_raw', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_press_release_raw_status', table_name='press_release_raw')
    op.drop_index('ix_press_release_raw_source_name_published_date', table_name='press_release_raw')
    op.drop_index('ix_press_release_raw_competitor_id', table_name='press_release_raw')
    op.drop_table('press_release_raw')
    # Note: PostgreSQL enum values cannot be dropped easily; leaving press_release in signal_type
