"""learning path, daily task and cf_rating

Revision ID: 0003
Revises: db3046096063
Create Date: 2026-07-27 00:00:00.000000

Task 10: 学习路径与推送引擎
- 给 problems 添加 cf_rating 字段（可空，加索引）
- 新增用户学习状态：user_knowledge_states、user_problem_acs、learning_profiles
- 新增学习路径：learning_paths、learning_path_items
- 新增当日任务：daily_tasks、daily_task_items

COMPAT: user_id 暂无外键（认证未实现），等 User 模型落地后单独迁移补 FK。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "db3046096063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Problem.cf_rating
    op.add_column(
        "problems",
        sa.Column("cf_rating", sa.Float(), nullable=True),
    )
    op.create_index(op.f("ix_problems_cf_rating"), "problems", ["cf_rating"], unique=False)

    # 2) Enums
    path_item_kind = postgresql.ENUM("normal", "remediation", name="path_item_kind", create_type=False)
    path_item_status = postgresql.ENUM(
        "pending", "active", "done", "skipped", name="path_item_status", create_type=False
    )
    daily_task_item_type = postgresql.ENUM(
        "lecture_card",
        "template_problem",
        "application_problem",
        "challenge_problem",
        name="daily_task_item_type",
        create_type=False,
    )
    daily_task_item_status = postgresql.ENUM("pending", "done", name="daily_task_item_status", create_type=False)
    for enum in (path_item_kind, path_item_status, daily_task_item_type, daily_task_item_status):
        enum.create(op.get_bind(), checkfirst=True)

    # 3) user_knowledge_states
    op.create_table(
        "user_knowledge_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "knowledge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_weak", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("consecutive_wa", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "knowledge_id", name="uq_user_knowledge"),
    )

    # 4) user_problem_acs
    op.create_table(
        "user_problem_acs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "problem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("problems.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "problem_id", name="uq_user_problem"),
    )

    # 5) learning_profiles
    op.create_table(
        "learning_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("target_rating_min", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("target_rating_max", sa.Integer(), nullable=False, server_default="1600"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_learning_profile_user"),
    )

    # 6) learning_paths
    op.create_table(
        "learning_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 7) learning_path_items
    op.create_table(
        "learning_path_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "path_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "knowledge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", path_item_kind, nullable=False, server_default="normal"),
        sa.Column("status", path_item_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 8) daily_tasks
    op.create_table(
        "daily_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("task_date", sa.Date(), nullable=False, index=True),
        sa.Column(
            "knowledge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_remediation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("missing_slots", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "task_date", name="uq_user_daily_task"),
    )

    # 9) daily_task_items
    op.create_table(
        "daily_task_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("daily_tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("item_type", daily_task_item_type, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "lecture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lectures.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "problem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("problems.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", daily_task_item_status, nullable=False, server_default="pending"),
        sa.Column("missing_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_task_items")
    op.drop_table("daily_tasks")
    op.drop_table("learning_path_items")
    op.drop_table("learning_paths")
    op.drop_table("learning_profiles")
    op.drop_table("user_problem_acs")
    op.drop_table("user_knowledge_states")

    for enum_name in (
        "daily_task_item_status",
        "daily_task_item_type",
        "path_item_status",
        "path_item_kind",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")

    op.drop_index(op.f("ix_problems_cf_rating"), table_name="problems")
    op.drop_column("problems", "cf_rating")
