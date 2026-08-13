from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgePoint


class ProblemDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ProblemStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ProblemSource(StrEnum):
    """题目来源（spec: 四层来源）。

    - PLATFORM: 平台自建题目（Task 7）
    - CODEFORCES: CF 外链题目（Task 8 同步）
    - ATCODER: AtCoder 外链题目（未来扩展）
    - USER_REPORTED: 用户自报题目（未来扩展）
    """

    PLATFORM = "platform"
    CODEFORCES = "codeforces"
    ATCODER = "atcoder"
    USER_REPORTED = "user_reported"


class Problem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "problems"
    # CF 外链题通过 (contest_id, index) 唯一约束保证幂等同步
    __table_args__ = (
        UniqueConstraint(
            "cf_contest_id",
            "cf_index",
            name="uq_problems_cf_contest_index",
        ),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[ProblemDifficulty] = mapped_column(
        SAEnum(
            ProblemDifficulty,
            name="problem_difficulty",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ProblemDifficulty.EASY,
    )
    status: Mapped[ProblemStatus] = mapped_column(
        SAEnum(
            ProblemStatus,
            name="problem_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ProblemStatus.DRAFT,
    )
    # 题目来源：platform 自建 / codeforces 外链 / atcoder / user_reported
    source: Mapped[ProblemSource] = mapped_column(
        SAEnum(
            ProblemSource,
            name="problem_source",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ProblemSource.PLATFORM,
    )
    # CF 外链题的 contest_id（用于 problemset.problems 同步匹配）
    cf_contest_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # CF 题目的 index（如 "A"、"B1"）
    cf_index: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # CF 外链 URL
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CF 题目标签（JSONB，如 ["dp", "greedy"]）
    cf_tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    time_limit_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    memory_limit_kb: Mapped[int] = mapped_column(Integer, nullable=False, default=262144)
    sample_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_sync_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hints: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    solution_template: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    test_cases: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    submit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Codeforces 题目 rating（CF 外链题目从 problemset.problems 同步；自建题目可空）
    # Task 10.4 推荐逻辑按此字段升序排序。
    cf_rating: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    knowledge_points: Mapped[list["KnowledgePoint"]] = relationship(
        "KnowledgePoint",
        secondary="problem_knowledge_points",
        back_populates="problems",
    )


class ProblemKnowledgePoint(Base):
    __tablename__ = "problem_knowledge_points"

    problem_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProblemVariant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "problem_variants"

    original_problem_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[ProblemDifficulty] = mapped_column(
        SAEnum(
            ProblemDifficulty,
            name="problem_difficulty",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    test_cases: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    time_limit_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    memory_limit_kb: Mapped[int] = mapped_column(Integer, nullable=False, default=262144)
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_preset: Mapped[bool] = mapped_column(default=False, nullable=False)

    original_problem: Mapped[Problem] = relationship(Problem, backref="variants")
