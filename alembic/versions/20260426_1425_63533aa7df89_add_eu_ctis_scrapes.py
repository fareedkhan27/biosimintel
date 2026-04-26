"""add_eu_ctis_scrapes

Revision ID: 63533aa7df89
Revises: 0533ffe570f2
Create Date: 2026-04-26 14:25:24.037352

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '63533aa7df89'
down_revision: Union[str, None] = '0533ffe570f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE signal_type ADD VALUE 'EU_CTIS_TRIAL'")

    op.create_table('eu_ctis_raw_scrapes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('scrape_date', sa.Date(), nullable=False),
        sa.Column('portal_url', sa.Text(), nullable=False),
        sa.Column('search_query', sa.Text(), nullable=False),
        sa.Column('total_results', sa.Integer(), nullable=True),
        sa.Column('raw_html', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scrape_date')
    )
    op.create_index('ix_eu_ctis_raw_scrapes_scrape_date', 'eu_ctis_raw_scrapes', ['scrape_date'], unique=False)

    op.create_table('eu_ctis_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_scrape_id', sa.UUID(), nullable=False),
        sa.Column('ctis_number', sa.Text(), nullable=False),
        sa.Column('sponsor_name', sa.Text(), nullable=True),
        sa.Column('trial_title', sa.Text(), nullable=False),
        sa.Column('intervention', sa.Text(), nullable=True),
        sa.Column('condition', sa.Text(), nullable=True),
        sa.Column('phase', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('eu_member_state', sa.Text(), nullable=True),
        sa.Column('decision_date', sa.Date(), nullable=True),
        sa.Column('ctis_url', sa.Text(), nullable=False),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('is_relevant', sa.Boolean(), nullable=False),
        sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_scrape_id'], ['eu_ctis_raw_scrapes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_eu_ctis_entries_ctis_number_decision_date', 'eu_ctis_entries', ['ctis_number', 'decision_date'], unique=False)
    op.create_index('ix_eu_ctis_entries_eu_member_state', 'eu_ctis_entries', ['eu_member_state'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_eu_ctis_entries_eu_member_state', table_name='eu_ctis_entries')
    op.drop_index('ix_eu_ctis_entries_ctis_number_decision_date', table_name='eu_ctis_entries')
    op.drop_table('eu_ctis_entries')
    op.drop_index('ix_eu_ctis_raw_scrapes_scrape_date', table_name='eu_ctis_raw_scrapes')
    op.drop_table('eu_ctis_raw_scrapes')
    # Note: PostgreSQL enum values cannot be dropped easily; leaving EU_CTIS_TRIAL in signal_type
