"""fix sandoz cik

Revision ID: 2a79a1bf08f0
Revises: 5853b13607d0
Create Date: 2026-04-22 23:24:58.430544

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2a79a1bf08f0'
down_revision: str | None = '5853b13607d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE competitors SET cik = '0000718877' WHERE id = 'f201a721-0dfa-45b9-8882-bc8b351a8090';"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE competitors SET cik = '0001114448' WHERE id = 'f201a721-0dfa-45b9-8882-bc8b351a8090';"
    )
