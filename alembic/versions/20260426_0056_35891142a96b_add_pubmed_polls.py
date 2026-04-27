"""add_pubmed_polls

Revision ID: 35891142a96b
Revises: 95b77a180751
Create Date: 2026-04-26 00:56:05.603065

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '35891142a96b'
down_revision: str | None = '95b77a180751'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new enum values to signal_type
    op.execute("ALTER TYPE signal_type ADD VALUE 'PUBLICATION_PHASE3'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'PUBLICATION_SAFETY'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'PUBLICATION_RWE'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'PUBLICATION_GENERAL'")

    op.create_table('pubmed_raw_polls',
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
    op.create_index('ix_pubmed_raw_polls_poll_date', 'pubmed_raw_polls', ['poll_date'], unique=False)

    op.create_table('pubmed_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_poll_id', sa.UUID(), nullable=False),
        sa.Column('pmid', sa.Text(), nullable=False),
        sa.Column('doi', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('authors', sa.Text(), nullable=True),
        sa.Column('journal', sa.Text(), nullable=True),
        sa.Column('pub_date', sa.Date(), nullable=True),
        sa.Column('article_url', sa.Text(), nullable=False),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('publication_type', sa.String(length=30), nullable=False),
        sa.Column('is_relevant', sa.Boolean(), nullable=False),
        sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_poll_id'], ['pubmed_raw_polls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pubmed_entries_pmid_pub_date', 'pubmed_entries', ['pmid', 'pub_date'], unique=False)
    op.create_index('ix_pubmed_entries_publication_type', 'pubmed_entries', ['publication_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pubmed_entries_publication_type', table_name='pubmed_entries')
    op.drop_index('ix_pubmed_entries_pmid_pub_date', table_name='pubmed_entries')
    op.drop_table('pubmed_entries')
    op.drop_index('ix_pubmed_raw_polls_poll_date', table_name='pubmed_raw_polls')
    op.drop_table('pubmed_raw_polls')
    # NOTE: PostgreSQL does not support removing enum values directly.
    # The publication enum values remain in signal_type until the type is rebuilt.
