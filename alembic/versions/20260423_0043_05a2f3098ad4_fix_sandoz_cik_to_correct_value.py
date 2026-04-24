"""fix_sandoz_cik_to_correct_value

Revision ID: 05a2f3098ad4
Revises: 5c5a5a8b9a6d
Create Date: 2026-04-23 00:43:51.037259

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '05a2f3098ad4'
down_revision: str | None = '5c5a5a8b9a6d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SANDOZ_ID = "f201a721-0dfa-45b9-8882-bc8b351a8090"
OLD_CIK = "0000718877"
NEW_CIK = "0001992829"


def upgrade() -> None:
    op.execute(
        f"UPDATE competitors SET cik = '{NEW_CIK}' WHERE id = '{SANDOZ_ID}';"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE competitors SET cik = '{OLD_CIK}' WHERE id = '{SANDOZ_ID}';"
    )
