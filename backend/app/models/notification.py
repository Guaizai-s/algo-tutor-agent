"""通知推送模型 (Task 12 智能推送引擎)。

通知类型：
- review_reminder: 复习提醒（艾宾浩斯遗忘曲线）
- daily_task: 当日任务推送
- path_update: 学习路径更新
- remediation: 补漏提醒
- system: 系统通知
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDMixin


class NotificationType(StrEnum):
    """通知类型。"""

    REVIEW_REMINDER = "review_reminder"
    DAILY_TASK = "daily_task"
    PATH_UPDATE = "path_update"
    REMEDIATION = "remediation"
    SYSTEM = "system"


class Notification(UUIDMixin, Base):
    """用户通知。

    COMPAT: user_id 暂无外键，等认证落地后补 FK。
    """

    __tablename__ = "notifications"

    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(
            NotificationType,
            name="notification_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 关联实体（可选）
    related_knowledge_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    related_problem_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
