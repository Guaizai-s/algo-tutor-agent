"""add cf_tag and cf_problem_count to knowledge_points

Revision ID: db3046096063
Revises: 0002
Create Date: 2026-07-25 03:06:27.807443

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db3046096063"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_points", sa.Column("cf_tag", sa.String(length=100), nullable=True))
    op.add_column(
        "knowledge_points",
        sa.Column("cf_problem_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(op.f("ix_knowledge_points_cf_tag"), "knowledge_points", ["cf_tag"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_points_cf_tag"), table_name="knowledge_points")
    op.drop_column("knowledge_points", "cf_problem_count")
    op.drop_column("knowledge_points", "cf_tag")
