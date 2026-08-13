"""add problem content sync state

Revision ID: c1f5a7249d0b
Revises: 630c3769419e
Create Date: 2026-08-14 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1f5a7249d0b"
down_revision: str | None = "630c3769419e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("problems", sa.Column("content_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("problems", sa.Column("content_sync_failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("problems", "content_sync_failed_at")
    op.drop_column("problems", "content_synced_at")
