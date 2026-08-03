"""create users table (Task 2.1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01 00:00:00.000000

Task 2: 用户认证（注册/登录/JWT）
- 新增 users 表：邮箱 + 密码哈希 + 角色 + ACM 档案字段
- 不修改其他表的 user_id 字段（COMPAT: 保持无外键的 UUID，避免破坏 Task 8/10/11）

字段：
- id: UUID 主键
- email: 唯一邮箱（登录用）
- username: 唯一用户名（显示用）
- hashed_password: bcrypt 哈希
- role: student/coach/admin，默认 student
- avatar: 可选头像 URL
- school/cf_handle/atcoder_handle/target_medal: ACM 档案（spec 2.2，本阶段全 nullable）
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 创建枚举类型（IF NOT EXISTS 避免重复）
    op.execute(
        "DO $$ BEGIN CREATE TYPE userrole AS ENUM ('student', 'coach', 'admin'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE targetmedal AS ENUM ('bronze', 'silver', 'gold'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # 2. 创建 users 表
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("student", "coach", "admin", name="userrole", create_type=False),
            nullable=False,
            server_default="student",
        ),
        sa.Column("avatar", sa.String(length=512), nullable=True),
        sa.Column("school", sa.String(length=255), nullable=True),
        sa.Column("cf_handle", sa.String(length=64), nullable=True),
        sa.Column("atcoder_handle", sa.String(length=64), nullable=True),
        sa.Column(
            "target_medal",
            postgresql.ENUM("bronze", "silver", "gold", name="targetmedal", create_type=False),
            nullable=True,
        ),
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
    )

    # 3. 唯一索引 + 普通索引
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_index(op.f("ix_users_cf_handle"), "users", ["cf_handle"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_cf_handle"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS targetmedal")
    op.execute("DROP TYPE IF EXISTS userrole")
