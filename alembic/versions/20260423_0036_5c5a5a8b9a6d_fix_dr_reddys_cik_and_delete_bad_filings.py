"""fix_dr_reddys_cik_and_delete_bad_filings

Revision ID: 5c5a5a8b9a6d
Revises: 2a79a1bf08f0
Create Date: 2026-04-23 00:36:01.452180

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5c5a5a8b9a6d'
down_revision: str | None = '2a79a1bf08f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DR_REDDYS_ID = "119be0da-40ed-4e3c-a36d-6703058e9fc7"
OLD_CIK = "0000895417"
NEW_CIK = "0001135951"


def upgrade() -> None:
    # Delete incorrect SEC filings fetched with the wrong CIK
    op.execute(
        f"DELETE FROM sec_filings WHERE competitor_id = '{DR_REDDYS_ID}';"
    )
    # Update Dr. Reddy's CIK to the correct value
    op.execute(
        f"UPDATE competitors SET cik = '{NEW_CIK}' WHERE id = '{DR_REDDYS_ID}';"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE competitors SET cik = '{OLD_CIK}' WHERE id = '{DR_REDDYS_ID}';"
    )
