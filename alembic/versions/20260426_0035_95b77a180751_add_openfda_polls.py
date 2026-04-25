"""add_openfda_polls

Revision ID: 95b77a180751
Revises: eb5b61b3dd69
Create Date: 2026-04-26 00:35:30.373524

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '95b77a180751'
down_revision: Union[str, None] = 'eb5b61b3dd69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum values to signal_type
    op.execute("ALTER TYPE signal_type ADD VALUE 'FDA_BIOSIMILAR_APPROVAL'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'FDA_LABEL_UPDATE'")
    op.execute("ALTER TYPE signal_type ADD VALUE 'FDA_PENDING_APPROVAL'")

    op.create_table('openfda_raw_polls',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('poll_date', sa.Date(), nullable=False),
        sa.Column('endpoint_url', sa.Text(), nullable=False),
        sa.Column('query_params', sa.JSON(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('poll_date')
    )
    op.create_index('ix_openfda_raw_polls_poll_date', 'openfda_raw_polls', ['poll_date'], unique=False)

    op.create_table('openfda_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('raw_poll_id', sa.UUID(), nullable=False),
        sa.Column('application_number', sa.Text(), nullable=True),
        sa.Column('brand_name', sa.Text(), nullable=True),
        sa.Column('generic_name', sa.Text(), nullable=True),
        sa.Column('manufacturer_name', sa.Text(), nullable=True),
        sa.Column('product_type', sa.Text(), nullable=True),
        sa.Column('submission_type', sa.Text(), nullable=True),
        sa.Column('submission_status', sa.Text(), nullable=True),
        sa.Column('approval_date', sa.Date(), nullable=True),
        sa.Column('openfda_url', sa.Text(), nullable=True),
        sa.Column('molecule_id', sa.UUID(), nullable=True),
        sa.Column('competitor_id', sa.UUID(), nullable=True),
        sa.Column('is_relevant', sa.Boolean(), nullable=False),
        sa.Column('signals_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['molecule_id'], ['molecules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_poll_id'], ['openfda_raw_polls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_openfda_entries_application_number_approval_date', 'openfda_entries', ['application_number', 'approval_date'], unique=False)
    op.create_index('ix_openfda_entries_generic_name_approval_date', 'openfda_entries', ['generic_name', 'approval_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_openfda_entries_generic_name_approval_date', table_name='openfda_entries')
    op.drop_index('ix_openfda_entries_application_number_approval_date', table_name='openfda_entries')
    op.drop_table('openfda_entries')
    op.drop_index('ix_openfda_raw_polls_poll_date', table_name='openfda_raw_polls')
    op.drop_table('openfda_raw_polls')
    # NOTE: PostgreSQL does not support removing enum values directly.
    # The FDA enum values remain in signal_type until the type is rebuilt.
