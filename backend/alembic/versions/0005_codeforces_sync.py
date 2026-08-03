"""codeforces sync: account, submission, rating_history, problem cf fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28 23:30:00.000000

Task 8: Codeforces 数据同步
- 新增 codeforces_accounts: 用户 CF 绑定档案 + 增量同步游标
- 新增 submissions: CF 提交记录元数据（不存源代码）
- 新增 rating_histories: CF Rating 曲线
- 扩展 problems: source / cf_contest_id / cf_index / external_url / cf_tags
  + (cf_contest_id, cf_index) 唯一约束保证 CF 题幂等同步

COMPAT: user_id 暂无外键（Task 2 用户认证未落地），沿用 Task 10/11 设计。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 扩展 problems 表：CF 外链字段
    # problem_source 枚举
    problem_source = postgresql.ENUM(
        "platform",
        "codeforces",
        "atcoder",
        "user_reported",
        name="problem_source",
        create_type=False,
    )
    # 先创建枚举类型（IF NOT EXISTS 避免重复）
    op.execute(
        "DO $$ BEGIN CREATE TYPE problem_source AS ENUM "
        "('platform', 'codeforces', 'atcoder', 'user_reported'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.add_column(
        "problems",
        sa.Column(
            "source",
            problem_source,
            nullable=False,
            server_default="platform",
        ),
    )
    op.add_column("problems", sa.Column("cf_contest_id", sa.Integer(), nullable=True))
    op.add_column("problems", sa.Column("cf_index", sa.String(length=8), nullable=True))
    op.add_column("problems", sa.Column("external_url", sa.Text(), nullable=True))
    op.add_column("problems", sa.Column("cf_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_problems_cf_contest_id", "problems", ["cf_contest_id"], unique=False)
    # CF 外链题唯一约束：(cf_contest_id, cf_index)
    # 使用普通 UNIQUE 约束（PostgreSQL 中多 NULL 不冲突，platform 题目不受影响）
    op.create_unique_constraint(
        "uq_problems_cf_contest_index",
        "problems",
        ["cf_contest_id", "cf_index"],
    )

    # 2. codeforces_accounts 表
    op.create_table(
        "codeforces_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("current_rating", sa.Integer(), nullable=True),
        sa.Column("last_submission_id", sa.BigInteger(), nullable=True),
        sa.Column("last_status_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rating_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handle", name="uq_codeforces_account_handle"),
        sa.UniqueConstraint("user_id", name="uq_codeforces_account_user"),
    )
    op.create_index("ix_codeforces_accounts_user_id", "codeforces_accounts", ["user_id"], unique=False)
    op.create_index("ix_codeforces_accounts_handle", "codeforces_accounts", ["handle"], unique=False)

    # 3. submissions 表
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cf_submission_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("problem_index", sa.String(length=8), nullable=False),
        sa.Column("handle_snapshot", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("programming_language", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_consumed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_consumed_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("passed_test_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("cf_submission_id", "user_id", name="uq_submission_cf_id_user"),
    )
    op.create_index("ix_submissions_cf_submission_id", "submissions", ["cf_submission_id"], unique=False)
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"], unique=False)
    op.create_index("ix_submissions_problem_id", "submissions", ["problem_id"], unique=False)
    op.create_index("ix_submissions_handle_snapshot", "submissions", ["handle_snapshot"], unique=False)
    op.create_index("ix_submissions_verdict", "submissions", ["verdict"], unique=False)
    op.create_index("ix_submissions_submitted_at", "submissions", ["submitted_at"], unique=False)

    # 4. rating_histories 表
    op.create_table(
        "rating_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("contest_name", sa.String(length=300), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("old_rating", sa.Integer(), nullable=False),
        sa.Column("new_rating", sa.Integer(), nullable=False),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "contest_id", name="uq_rating_history_user_contest"),
    )
    op.create_index("ix_rating_histories_user_id", "rating_histories", ["user_id"], unique=False)
    op.create_index("ix_rating_histories_handle", "rating_histories", ["handle"], unique=False)
    op.create_index("ix_rating_histories_rated_at", "rating_histories", ["rated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rating_histories_rated_at", table_name="rating_histories")
    op.drop_index("ix_rating_histories_handle", table_name="rating_histories")
    op.drop_index("ix_rating_histories_user_id", table_name="rating_histories")
    op.drop_table("rating_histories")

    op.drop_index("ix_submissions_submitted_at", table_name="submissions")
    op.drop_index("ix_submissions_verdict", table_name="submissions")
    op.drop_index("ix_submissions_handle_snapshot", table_name="submissions")
    op.drop_index("ix_submissions_problem_id", table_name="submissions")
    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_index("ix_submissions_cf_submission_id", table_name="submissions")
    op.drop_table("submissions")

    op.drop_index("ix_codeforces_accounts_handle", table_name="codeforces_accounts")
    op.drop_index("ix_codeforces_accounts_user_id", table_name="codeforces_accounts")
    op.drop_table("codeforces_accounts")

    op.drop_constraint("uq_problems_cf_contest_index", "problems", type_="unique")
    op.drop_index("ix_problems_cf_contest_id", table_name="problems")
    op.drop_column("problems", "cf_tags")
    op.drop_column("problems", "external_url")
    op.drop_column("problems", "cf_index")
    op.drop_column("problems", "cf_contest_id")
    op.drop_column("problems", "source")
    op.execute("DROP TYPE IF EXISTS problem_source")
