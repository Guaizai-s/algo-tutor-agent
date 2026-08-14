"""cleanup mock Codeforces verification data

Revision ID: a61c9d70e2f4
Revises: d94f2a6c718b
Create Date: 2026-08-15 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a61c9d70e2f4"
down_revision: str | None = "d94f2a6c718b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Older versions of scripts.verify_cf_sync_manual committed fake accounts.
    # Remove only the reserved handle prefix and reserved fake contest IDs.
    statements = [
        """
        DELETE FROM wrongbook_entries
        WHERE user_id IN (
            SELECT user_id FROM codeforces_accounts WHERE handle LIKE 'mock_user_%'
        )
        """,
        """
        DELETE FROM user_problem_acs
        WHERE user_id IN (
            SELECT user_id FROM codeforces_accounts WHERE handle LIKE 'mock_user_%'
        )
        """,
        """
        DELETE FROM rating_histories
        WHERE user_id IN (
            SELECT user_id FROM codeforces_accounts WHERE handle LIKE 'mock_user_%'
        )
        """,
        """
        DELETE FROM submissions
        WHERE user_id IN (
            SELECT user_id FROM codeforces_accounts WHERE handle LIKE 'mock_user_%'
        )
        """,
        "DELETE FROM codeforces_accounts WHERE handle LIKE 'mock_user_%'",
        """
        DELETE FROM problems
        WHERE source = 'codeforces' AND cf_contest_id IN (900001, 900002)
        """,
    ]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    # Removed verification rows are intentionally not recreated.
    pass
