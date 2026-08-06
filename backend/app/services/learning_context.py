"""为 OpenAI Tutor 构建最小、可信且不含敏感字段的学习上下文。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import (
    LearningPath,
    LearningPathItem,
    LearningProfile,
    UserKnowledgeState,
)
from app.models.problem import Problem
from app.models.user import User
from app.models.wrongbook import WrongBookEntry


async def build_tutor_learning_context(db: AsyncSession, user_id: UUID) -> str | None:
    """汇总目标、薄弱点、当前路径和未解决错题，不发送邮箱或学校信息。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return None

    profile = (
        await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))
    ).scalar_one_or_none()
    weak_rows = (
        await db.execute(
            select(
                KnowledgePoint.name,
                UserKnowledgeState.mastery,
                UserKnowledgeState.consecutive_wa,
            )
            .join(KnowledgePoint, KnowledgePoint.id == UserKnowledgeState.knowledge_id)
            .where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.is_weak.is_(True),
            )
            .order_by(UserKnowledgeState.mastery.asc(), KnowledgePoint.order.asc())
            .limit(5)
        )
    ).all()
    path_rows = (
        await db.execute(
            select(
                KnowledgePoint.name,
                LearningPathItem.kind,
                LearningPathItem.status,
            )
            .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
            .join(KnowledgePoint, KnowledgePoint.id == LearningPathItem.knowledge_id)
            .where(
                LearningPath.user_id == user_id,
                LearningPath.is_active.is_(True),
            )
            .order_by(LearningPathItem.position.asc())
            .limit(5)
        )
    ).all()
    wrong_rows = (
        await db.execute(
            select(Problem.title, WrongBookEntry.verdict, WrongBookEntry.retry_count)
            .join(Problem, Problem.id == WrongBookEntry.problem_id)
            .where(
                WrongBookEntry.user_id == user_id,
                WrongBookEntry.resolved.is_(False),
            )
            .order_by(WrongBookEntry.created_at.desc())
            .limit(3)
        )
    ).all()

    target = (
        f"{profile.target_rating_min}-{profile.target_rating_max}"
        if profile is not None
        else "尚未定标"
    )
    lines = [
        f"学习者：{user.username}",
        f"Codeforces：{user.cf_handle or '未绑定'}",
        f"目标 Rating：{target}",
    ]
    if weak_rows:
        lines.append(
            "薄弱点："
            + "；".join(
                f"{row.name}(掌握度 {row.mastery:.0%}, 连续错误 {row.consecutive_wa})"
                for row in weak_rows
            )
        )
    else:
        lines.append("薄弱点：暂无已确认薄弱点")
    if path_rows:
        lines.append(
            "当前路径："
            + " → ".join(
                f"{row.name}[{row.kind.value}/{row.status.value}]" for row in path_rows
            )
        )
    if wrong_rows:
        lines.append(
            "待订正错题："
            + "；".join(
                f"{row.title}({row.verdict}, 已重试 {row.retry_count} 次)" for row in wrong_rows
            )
        )
    return "\n".join(lines)
