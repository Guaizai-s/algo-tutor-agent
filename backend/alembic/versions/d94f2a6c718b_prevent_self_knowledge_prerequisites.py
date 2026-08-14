"""prevent self knowledge prerequisites

Revision ID: d94f2a6c718b
Revises: c1f5a7249d0b
Create Date: 2026-08-14 23:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d94f2a6c718b"
down_revision: str | None = "c1f5a7249d0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM knowledge_prerequisites
        WHERE knowledge_id = prerequisite_id
        """
    )
    op.create_check_constraint(
        "ck_knowledge_prerequisites_not_self",
        "knowledge_prerequisites",
        "knowledge_id <> prerequisite_id",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_knowledge_prerequisites_not_self",
        "knowledge_prerequisites",
        type_="check",
    )
