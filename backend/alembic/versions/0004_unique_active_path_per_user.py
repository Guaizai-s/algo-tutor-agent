"""unique active learning path per user

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27 00:01:00.000000

Task 10 修复：保证每个用户同一时间只有一条 active 路径，避免并发
创建重复路径。daily_tasks 已有 (user_id, task_date) 唯一约束，但
learning_paths 缺少 active 唯一性保证。

通过部分唯一索引实现：每个 user_id 只允许一条 is_active=TRUE 的记录。
并发 INSERT 时数据库会拒绝第二条并抛 IntegrityError，service 层
捕获后回退到读已存在的 active 路径。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 部分唯一索引：每个 user_id 只能有一条 is_active=TRUE 的路径
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_paths_active_per_user "
        "ON learning_paths (user_id) WHERE is_active = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_learning_paths_active_per_user")
