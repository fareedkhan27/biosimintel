"""add_ema_epar_polls

Revision ID: 19862056e634
Revises: 2393ab056ab4
Create Date: 2026-04-25 21:32:30.191616

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '19862056e634'
down_revision: Union[str, None] = '2393ab056ab4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum value to signal_type
    op.execute("ALTER TYPE signal_type ADD VALUE 'EMA_EPAR_APPROVAL'")

    op.create_table('ema_epar_raw_polls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('poll_date', sa.Date(), nullable=False),
    sa.Column('endpoint_url', sa.Text(), nullable=False),
    sa.Column('raw_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('poll_date')
    )
    op.create_index('ix_ema_epar_raw_polls_poll_date', 'ema_epar_raw_polls', ['poll_date'], unique=False)
    op.create_table('ema_epar_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('raw_poll_id', sa.UUID(), nullable=False),
    sa.Column('product_name', sa.Text(), nullable=False),
    sa.Column('active_substance', sa.Text(), nullable=False),
    sa.Column('marketing_authorisation_holder', sa.Text(), nullable=False),
    sa.Column('authorisation_status', sa.Text(), nullable=False),
    sa.Column('indication', sa.Text(), nullable=True),
    sa.Column('decision_date', sa.Date(), nullable=True),
    sa.Column('epar_url', sa.Text(), nullable=False),
    sa.Column('molecule_id', sa.UUID(), nullable=True),
    sa.Column('competitor_id', sa.UUID(), nullable=True),
    sa.Column('is_relevant', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['raw_poll_id'], ['ema_epar_raw_polls.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ema_epar_entries_active_substance_decision_date', 'ema_epar_entries', ['active_substance', 'decision_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ema_epar_entries_active_substance_decision_date', table_name='ema_epar_entries')
    op.drop_table('ema_epar_entries')
    op.drop_index('ix_ema_epar_raw_polls_poll_date', table_name='ema_epar_raw_polls')
    op.drop_table('ema_epar_raw_polls')
    # NOTE: PostgreSQL does not support removing enum values directly.
    # The 'ema_epar_approval' enum value remains in signal_type until the type is rebuilt.
