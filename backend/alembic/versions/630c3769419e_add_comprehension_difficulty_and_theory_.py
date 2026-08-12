"""add comprehension_difficulty and theory_depth to knowledge_points

Revision ID: 630c3769419e
Revises: 20c16bf2008a
Create Date: 2026-08-12 10:48:11.931745

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "630c3769419e"
down_revision: str | None = "20c16bf2008a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_points", sa.Column("comprehension_difficulty", sa.SmallInteger(), nullable=False, server_default="1")
    )
    op.add_column("knowledge_points", sa.Column("theory_depth", sa.SmallInteger(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("knowledge_points", "theory_depth")
    op.drop_column("knowledge_points", "comprehension_difficulty")
