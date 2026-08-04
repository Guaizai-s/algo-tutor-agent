"""Codeforces 同步相关模型 (Task 8)。

包含：
- CodeforcesAccount: 用户 CF 绑定档案（COMPAT: user_id 暂无外键，等 User 表落地后补）
- Submission: CF 提交记录元数据（严禁保存源代码）
- RatingHistory: CF Rating 历史曲线

设计原则：
- 所有同步写入必须幂等（基于 CF submission_id / contest_id+rated_at 唯一约束）
- 不保存源代码、不保存题面正文
- 不依赖 User 表（沿用 Task 10/11 的 COMPAT 设计）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.problem import Problem


class CodeforcesAccount(UUIDMixin, TimestampMixin, Base):
    """用户 Codeforces 绑定档案。

    COMPAT: user_id 暂无外键（Task 2 用户认证未落地），沿用 Task 10/11 的设计。
    每个 user_id 只能绑定一个 handle（唯一）。
    记录增量同步游标，避免重复拉取历史 submission。
    """

    __tablename__ = "codeforces_accounts"
    __table_args__ = (UniqueConstraint("handle", name="uq_codeforces_account_handle"),)

    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 增量同步游标：CF submission id 是单调递增的，用它做幂等依据
    last_submission_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_status_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rating_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Submission(UUIDMixin, TimestampMixin, Base):
    """CF 提交记录元数据。

    严禁保存源代码 —— CF API user.status 不返回源代码，本表也不存。
    通过 (cf_submission_id, user_id) 唯一约束保证幂等。
    problem_id 可为空：若 CF 题目尚未同步到 Problem 表，则不关联。
    """

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("cf_submission_id", "user_id", name="uq_submission_cf_id_user"),)

    # CF 的 submission id 是 int64 范围，用 BigInteger
    cf_submission_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # COMPAT: user_id 暂无外键
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    # 可空：CF Problem 未同步时无法关联
    problem_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # CF 题目的 contest_id + index，用于幂等匹配 Problem
    contest_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    problem_index: Mapped[str] = mapped_column(String(8), nullable=False)
    # handle 快照（用户可能换 handle，但 submission 永远属于当时绑定的 handle）
    handle_snapshot: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    programming_language: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    time_consumed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memory_consumed_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    passed_test_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    problem: Mapped[Problem | None] = relationship("Problem")


class RatingHistory(UUIDMixin, TimestampMixin, Base):
    """CF Rating 历史曲线。

    通过 (user_id, contest_id) 唯一约束保证重复同步幂等。
    """

    __tablename__ = "rating_histories"
    __table_args__ = (UniqueConstraint("user_id", "contest_id", name="uq_rating_history_user_contest"),)

    # COMPAT: user_id 暂无外键
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    handle: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contest_id: Mapped[int] = mapped_column(Integer, nullable=False)
    contest_name: Mapped[str] = mapped_column(String(300), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    old_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    new_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    rated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
