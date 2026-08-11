"""add lecture source and rewrite fields

Revision ID: 3846ec5748ed
Revises: 8fe6246fd27c
Create Date: 2026-08-10 22:43:53.406063

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3846ec5748ed"
down_revision: str | None = "8fe6246fd27c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    lecture_source_enum = sa.Enum("oi_wiki", "zuo_lecture", "ai_generated", "ai_rewritten", name="lecture_source")
    lecture_source_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("lectures", sa.Column("source", lecture_source_enum, nullable=False, server_default="oi_wiki"))
    op.add_column("lectures", sa.Column("source_lecture_id", sa.UUID(), nullable=True))
    op.add_column("lectures", sa.Column("rewrite_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("lectures", sa.Column("generation_prompt_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key(None, "lectures", "lectures", ["source_lecture_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(None, "lectures", type_="foreignkey")
    op.drop_column("lectures", "generation_prompt_hash")
    op.drop_column("lectures", "rewrite_version")
    op.drop_column("lectures", "source_lecture_id")
    op.drop_column("lectures", "source")
    sa.Enum(name="lecture_source").drop(op.get_bind(), checkfirst=True)
    # ### end Alembic commands ###
