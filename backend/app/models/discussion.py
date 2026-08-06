"""讨论区模型 (Task 15)。

包含：
- Discussion: 讨论帖（可分板块：综合讨论 / 题目问答 / 经验分享 / 建议反馈）
- DiscussionComment: 讨论回复（支持嵌套）

COMPAT: author_id 暂无外键，等 User 模型落地后补 FK。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgePoint
    from app.models.problem import Problem


class DiscussionCategory(StrEnum):
    GENERAL = "general"  # 综合讨论
    QUESTION = "question"  # 题目问答
    EXPERIENCE = "experience"  # 经验分享
    SUGGESTION = "suggestion"  # 建议反馈


class Discussion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "discussions"

    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    author_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[DiscussionCategory] = mapped_column(
        SAEnum(
            DiscussionCategory,
            name="discussion_category",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=DiscussionCategory.GENERAL,
    )
    # 可选关联知识点
    knowledge_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 可选关联题目
    problem_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    knowledge: Mapped[KnowledgePoint | None] = relationship("KnowledgePoint")
    problem: Mapped[Problem | None] = relationship("Problem")
    comments: Mapped[list[DiscussionComment]] = relationship(
        "DiscussionComment",
        back_populates="discussion",
        cascade="all, delete-orphan",
        order_by="DiscussionComment.created_at",
    )


class DiscussionComment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "discussion_comments"

    discussion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discussions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # COMPAT: 认证落地后改为 ForeignKey("users.id")
    author_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discussion_comments.id", ondelete="CASCADE"),
        nullable=True,
    )

    discussion: Mapped[Discussion] = relationship("Discussion", back_populates="comments")
    parent: Mapped[DiscussionComment | None] = relationship(
        "DiscussionComment", remote_side="DiscussionComment.id", backref="replies"
    )
