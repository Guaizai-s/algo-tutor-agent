"""错题本模型 (Task 12)。

独立于 Submission 模型（Role B 领地），避免跨区修改。
通过 submission_id 关联提交记录，追踪重试和解决状态。

COMPAT: user_id 暂无外键，等 User 模型落地后补 FK。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.codeforces import Submission
    from app.models.problem import Problem


class WrongBookEntry(UUIDMixin, TimestampMixin, Base):
    """错题本条目。

    每个最终失败 verdict（如 WA/TLE/RE/CE）的 submission 对应一条记录。
    通过 (submission_id, user_id) 唯一约束保证幂等。
    """

    __tablename__ = "wrongbook_entries"
    __table_args__ = (UniqueConstraint("submission_id", "user_id", name="uq_wrongbook_submission_user"),)

    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submission: Mapped[Submission] = relationship("Submission", backref="wrongbook_entry")
    problem: Mapped[Problem | None] = relationship("Problem")
