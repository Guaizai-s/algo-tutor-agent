"""User model (Task 2).

认证未完成前的 COMPAT 约束（见 project_memory）：
- 其他表的 user_id 字段保持无外键的 UUID，不改为 ForeignKey("users.id")
- 这避免 Task 8/10/11 的现有迁移和测试被破坏
- 本表只创建 users 表本身，不动其他表

字段：
- id: UUID 主键
- email: 唯一邮箱（登录用）
- username: 唯一用户名（显示用）
- hashed_password: bcrypt 哈希
- role: student/coach/admin，默认 student
- avatar: 可选头像 URL
- ACM 档案字段（spec 2.2，本阶段全部 nullable，后续 PATCH /auth/profile 补充）
  - school: 学校
  - cf_handle: Codeforces handle（绑定流程在 Task 2.3，不在 2.1）
  - atcoder_handle: AtCoder handle
  - target_medal: 目标奖牌梯度 bronze/silver/gold
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserRole(StrEnum):
    """用户角色（小写枚举值，与前端 TypeScript 类型对齐）。"""

    STUDENT = "student"
    COACH = "coach"
    ADMIN = "admin"


class TargetMedal(StrEnum):
    """目标奖牌梯度（spec 2.2）。"""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class User(UUIDMixin, TimestampMixin, Base):
    """平台用户。

    COMPAT: 本表落地后不立即给其他表的 user_id 加外键，避免破坏 Task 8/10/11。
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=UserRole.STUDENT,
        server_default=UserRole.STUDENT.value,
    )
    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ACM 档案字段（spec 2.2，本阶段全部 nullable）
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cf_handle: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    atcoder_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_medal: Mapped[TargetMedal | None] = mapped_column(
        SAEnum(TargetMedal, values_callable=lambda enum: [item.value for item in enum]),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email})>"
