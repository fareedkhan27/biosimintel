"""add_who_ictrp_polls

Revision ID: 1f46d2d80202
Revises: 7480bc600546
Create Date: 2026-04-26 13:23:51.893084

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1f46d2d80202'
down_revision: Union[str, None] = '7480bc600546'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('who_ictrp_raw_polls',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('poll_month', sa.Text(), nullable=False),
        sa.Column('download_url', sa.Text(), nullable=False),
        sa.Column('csv_filename', sa.Text(), nullable=True),
        sa.Column('total_rows', sa.Integer(), nullable=True),
        sa.Column('filtered_rows', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('poll_month')
    )
    op.create_index('ix_who_ictrp_raw_polls_poll_month', 'who_ictrp_raw_polls', ['poll_month'], unique=False)

    op.create_table('who_ictrp_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_poll_id', sa.UUID(), nullable=False),
        sa.Column('trial_id', sa.Text(), nullable=False),
        sa.Column('reg_id', sa.Text(), nullable=True),
        sa.Column('public_title', sa.Text(), nullable=False),
        sa.Column('scientific_title', sa.Text(), nullable=True),
        sa.Column('intervention', sa.Text(), nullable=True),
        sa.Column('condition', sa.Text(), nullable=True),
        sa.Column('recruitment_status', sa.Text(), nullable=True),
        sa.Column('phase', sa.Text(), nullable=True),
        sa.Column('study_type', sa.Text(), nullable=True),
        sa.Column('date_registration', sa.Date(), nullable=True),
        sa.Column('date_enrolment', sa.Date(), nullable=True),
        sa.Column('countries', sa.Text(), nullable=True),
        sa.Column('source_register', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('is_relevant', sa.Boolean(), nullable=False),
        sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_poll_id'], ['who_ictrp_raw_polls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_who_ictrp_entries_trial_id_date_registration', 'who_ictrp_entries', ['trial_id', 'date_registration'], unique=False)
    op.create_index('ix_who_ictrp_entries_source_register', 'who_ictrp_entries', ['source_register'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_who_ictrp_entries_source_register', table_name='who_ictrp_entries')
    op.drop_index('ix_who_ictrp_entries_trial_id_date_registration', table_name='who_ictrp_entries')
    op.drop_table('who_ictrp_entries')
    op.drop_index('ix_who_ictrp_raw_polls_poll_month', table_name='who_ictrp_raw_polls')
    op.drop_table('who_ictrp_raw_polls')
