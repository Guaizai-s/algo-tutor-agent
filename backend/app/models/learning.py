"""学习路径与推送引擎相关模型（Task 10）。

包含：
- UserKnowledgeState: 用户-知识点掌握度、weak 标记、连续 WA 计数
- UserProblemAC: 用户-题目 AC 状态（用于推荐排除已 AC 题目）
- UserLearningProfile: 用户训练目标 rating 区间（铜/银/金/高级）
- LearningPath / LearningPathItem: 用户当前学习路径及路径项目
- DailyTask / DailyTaskItem: 当日任务及任务项

过渡设计说明：
- 认证未实现，user_id 使用无外键的 UUID，标注 COMPAT 注释。
- Task 11 的完整进度面板、雷达图、Rating 曲线不在此实现。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgePoint
    from app.models.problem import Problem


# mastery 阈值常量，供 service 层共享
MASTERY_THRESHOLD = 0.8
WEAK_MASTERY_THRESHOLD = 0.5
CONSECUTIVE_WA_THRESHOLD = 3


class UserKnowledgeState(UUIDMixin, TimestampMixin, Base):
    """用户-知识点掌握度状态。

    COMPAT: user_id 暂无外键，等 User 模型落地后再补 FK。
    """

    __tablename__ = "user_knowledge_states"
    __table_args__ = (UniqueConstraint("user_id", "knowledge_id", name="uq_user_knowledge"),)

    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_weak: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consecutive_wa: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    knowledge: Mapped[KnowledgePoint] = relationship("KnowledgePoint")


class UserProblemAC(UUIDMixin, TimestampMixin, Base):
    """用户-题目 AC 状态。

    COMPAT: user_id 暂无外键。
    仅记录是否 AC，不存源代码、不存 verdict 历史。
    """

    __tablename__ = "user_problem_acs"
    __table_args__ = (UniqueConstraint("user_id", "problem_id", name="uq_user_problem"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    problem_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    problem: Mapped[Problem] = relationship("Problem")


class LearningProfile(UUIDMixin, TimestampMixin, Base):
    """用户学习画像：训练目标 rating 区间。

    COMPAT: user_id 暂无外键。
    按 spec：CF Rating <1200 铜牌向 / 1200-1600 银牌向 / 1600-2000 金牌向 / >2000 高级向。
    """

    __tablename__ = "learning_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_learning_profile_user"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    target_rating_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    target_rating_max: Mapped[int] = mapped_column(Integer, nullable=False, default=1600)


class PathItemKind(StrEnum):
    """路径项目类型。"""

    NORMAL = "normal"  # 普通学习任务
    REMEDIATION = "remediation"  # 补漏任务


class PathItemStatus(StrEnum):
    """路径项目状态。"""

    PENDING = "pending"  # 未解锁（前置未满足）
    ACTIVE = "active"  # 当前可学
    DONE = "done"  # 已完成（mastery ≥ 0.8）
    SKIPPED = "skipped"  # 已掌握，跳过


class LearningPath(UUIDMixin, TimestampMixin, Base):
    """用户当前学习路径。

    COMPAT: user_id 暂无外键。
    一个用户同一时间只有一条 active 路径；重新 generate 时将旧的标记为 archived。
    """

    __tablename__ = "learning_paths"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    items: Mapped[list[LearningPathItem]] = relationship(
        "LearningPathItem",
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="LearningPathItem.position",
    )


class LearningPathItem(UUIDMixin, TimestampMixin, Base):
    """学习路径项目。"""

    __tablename__ = "learning_path_items"

    path_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[PathItemKind] = mapped_column(
        SAEnum(
            PathItemKind,
            name="path_item_kind",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PathItemKind.NORMAL,
    )
    status: Mapped[PathItemStatus] = mapped_column(
        SAEnum(
            PathItemStatus,
            name="path_item_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=PathItemStatus.PENDING,
    )

    path: Mapped[LearningPath] = relationship("LearningPath", back_populates="items")
    knowledge: Mapped[KnowledgePoint] = relationship("KnowledgePoint")


class DailyTaskItemType(StrEnum):
    """当日任务项类型。"""

    LECTURE_CARD = "lecture_card"
    TEMPLATE_PROBLEM = "template_problem"
    APPLICATION_PROBLEM = "application_problem"
    CHALLENGE_PROBLEM = "challenge_problem"


class DailyTaskItemStatus(StrEnum):
    """当日任务项完成状态。"""

    PENDING = "pending"
    DONE = "done"


class DailyTask(UUIDMixin, TimestampMixin, Base):
    """当日任务计划。

    COMPAT: user_id 暂无外键。
    同一用户、同一自然日只有一条记录（幂等）。
    """

    __tablename__ = "daily_tasks"
    __table_args__ = (UniqueConstraint("user_id", "task_date", name="uq_user_daily_task"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    task_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_remediation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 缺失槽位（如 ["challenge_problem"] 表示挑战题不足）
    missing_slots: Mapped[list[str]] = mapped_column(
        # JSONB? 这里用 String 简化；service 层序列化为逗号分隔
        String(500),
        nullable=False,
        default="",
    )

    items: Mapped[list[DailyTaskItem]] = relationship(
        "DailyTaskItem",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="DailyTaskItem.position",
    )
    knowledge: Mapped[KnowledgePoint] = relationship("KnowledgePoint")


class DailyTaskItem(UUIDMixin, TimestampMixin, Base):
    """当日任务项。"""

    __tablename__ = "daily_task_items"

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("daily_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[DailyTaskItemType] = mapped_column(
        SAEnum(
            DailyTaskItemType,
            name="daily_task_item_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    lecture_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="SET NULL"),
        nullable=True,
    )
    problem_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[DailyTaskItemStatus] = mapped_column(
        SAEnum(
            DailyTaskItemStatus,
            name="daily_task_item_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=DailyTaskItemStatus.PENDING,
    )
    # 冗余存储缺失原因（如 "no published problem in rating range"）
    missing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[DailyTask] = relationship("DailyTask", back_populates="items")


class CheckIn(UUIDMixin, TimestampMixin, Base):
    """每日打卡记录（Task 11.1）。

    COMPAT: user_id 暂无外键。
    同一用户、同一自然日只有一条记录（幂等）。
    用于计算连续打卡天数（streak）。
    """

    __tablename__ = "check_ins"
    __table_args__ = (UniqueConstraint("user_id", "check_date", name="uq_check_in_user_date"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    check_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ReviewStage(StrEnum):
    """艾宾浩斯遗忘曲线阶段（Task 13）。"""

    INITIAL = "initial"  # 首次学习
    STAGE_1 = "stage_1"  # 1 天后
    STAGE_2 = "stage_2"  # 2 天后
    STAGE_3 = "stage_3"  # 4 天后
    STAGE_4 = "stage_4"  # 7 天后
    STAGE_5 = "stage_5"  # 15 天后
    STAGE_6 = "stage_6"  # 30 天后
    COMPLETED = "completed"  # 复习完成


# 遗忘临界点：学习后经过的天数 → 下一阶段
REVIEW_INTERVALS: dict[ReviewStage, int] = {
    ReviewStage.INITIAL: 1,
    ReviewStage.STAGE_1: 2,
    ReviewStage.STAGE_2: 4,
    ReviewStage.STAGE_3: 7,
    ReviewStage.STAGE_4: 15,
    ReviewStage.STAGE_5: 30,
}

# 阶段推进顺序
REVIEW_STAGE_ORDER: list[ReviewStage] = [
    ReviewStage.INITIAL,
    ReviewStage.STAGE_1,
    ReviewStage.STAGE_2,
    ReviewStage.STAGE_3,
    ReviewStage.STAGE_4,
    ReviewStage.STAGE_5,
    ReviewStage.STAGE_6,
    ReviewStage.COMPLETED,
]


class ReviewRecord(UUIDMixin, TimestampMixin, Base):
    """艾宾浩斯复习记录（Task 13）。

    COMPAT: user_id 暂无外键。
    每个用户-知识点只有一条复习记录，追踪遗忘曲线阶段。
    """

    __tablename__ = "review_records"
    __table_args__ = (UniqueConstraint("user_id", "knowledge_id", name="uq_review_record_user_kp"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[ReviewStage] = mapped_column(
        SAEnum(
            ReviewStage,
            name="review_stage",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ReviewStage.INITIAL,
    )
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    knowledge: Mapped[KnowledgePoint] = relationship("KnowledgePoint")
