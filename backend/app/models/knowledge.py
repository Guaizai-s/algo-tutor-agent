from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.problem import Problem


class KnowledgePointDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class KnowledgePoint(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_points"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[KnowledgePointDifficulty] = mapped_column(
        SAEnum(
            KnowledgePointDifficulty,
            name="knowledge_difficulty",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=KnowledgePointDifficulty.EASY,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Codeforces 关联（CF tag 合并到知识点时填）
    cf_tag: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cf_problem_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    parent: Mapped["KnowledgePoint | None"] = relationship(
        "KnowledgePoint", remote_side="KnowledgePoint.id", back_populates="children"
    )
    children: Mapped[list["KnowledgePoint"]] = relationship("KnowledgePoint", back_populates="parent", cascade="all")
    prerequisites: Mapped[list["KnowledgePrerequisite"]] = relationship(
        "KnowledgePrerequisite",
        foreign_keys="KnowledgePrerequisite.knowledge_id",
        back_populates="knowledge",
        cascade="all, delete-orphan",
    )
    problems: Mapped[list["Problem"]] = relationship(
        "Problem", secondary="problem_knowledge_points", back_populates="knowledge_points"
    )


class KnowledgePrerequisite(UUIDMixin, Base):
    __tablename__ = "knowledge_prerequisites"

    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    )

    knowledge: Mapped[KnowledgePoint] = relationship(
        KnowledgePoint, foreign_keys=[knowledge_id], back_populates="prerequisites"
    )
    prerequisite: Mapped[KnowledgePoint] = relationship(KnowledgePoint, foreign_keys=[prerequisite_id])


class LectureLevel(StrEnum):
    CARD = "card"
    STANDARD = "standard"
    DEEP = "deep"


class Lecture(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "lectures"

    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[LectureLevel] = mapped_column(
        SAEnum(
            LectureLevel,
            name="lecture_level",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    knowledge: Mapped[KnowledgePoint] = relationship(KnowledgePoint, backref="lectures")


class CodeTemplate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "code_templates"

    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    template_code: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    knowledge: Mapped[KnowledgePoint] = relationship(KnowledgePoint, backref="code_templates")
