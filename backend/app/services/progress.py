"""学习进度与掌握度 service (Task 11)。

核心职责：
- 聚合查询进度面板数据（知识点数、AC 数、通过率、雷达图、薄弱点）
- 按 spec 计算 mastery = AC 题数 / 该知识点关联题目总数
- 弱项诊断：0 < mastery < 0.5 标记 is_weak

数据源：
- UserKnowledgeState: 用户-知识点 mastery + is_weak
- UserProblemAC: 用户-题目 AC 状态
- LearningProfile: 用户训练目标 rating 区间
- KnowledgePoint / Problem / ProblemKnowledgePoint: 全量元数据
- Submission (Task 8): 连续打卡天数 streak_days
- RatingHistory (Task 8): CF Rating 曲线

COMPAT 设计：
- user_id 显式传入（无外键，等 Task 2 认证落地后改 token）

严格遵循 spec 第 256-278 行的分级规则：
- 无提交：未学
- 0 < mastery < 0.5：薄弱
- 0.5 ≤ mastery < 0.8：基本掌握
- mastery ≥ 0.8 且 AC ≥ 3：已掌握
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.codeforces import RatingHistory, Submission
from app.models.knowledge import KnowledgePoint
from app.models.learning import (
    MASTERY_THRESHOLD,
    WEAK_MASTERY_THRESHOLD,
    LearningProfile,
    UserKnowledgeState,
    UserProblemAC,
)
from app.models.problem import Problem, ProblemKnowledgePoint, ProblemStatus
from app.models.wrongbook import WrongBookEntry
from app.schemas.progress import (
    MasteryByCategory,
    ProgressOverviewResponse,
    RatingHistoryPoint,
    RecomputeMasteryResponse,
    TargetProgress,
)

logger = logging.getLogger(__name__)

# spec: 已掌握要求 AC ≥ 3
MASTERED_MIN_AC_COUNT = 3


async def get_progress_overview(db: AsyncSession, user_id: UUID) -> ProgressOverviewResponse:
    """聚合查询用户进度面板数据。

    所有查询均为只读，不修改数据库。
    """
    # 1. 知识点总数
    total_kp = (await db.execute(select(func.count(KnowledgePoint.id)))).scalar_one()

    # 2. 用户已掌握知识点数（mastery >= 0.8 且 AC >= 3 且非 weak）
    mastered_kp = await _count_mastered_knowledge(db, user_id)

    # 3. 已发布题目总数
    total_problems = (
        await db.execute(select(func.count(Problem.id)).where(Problem.status == ProblemStatus.PUBLISHED))
    ).scalar_one()

    # 4. 用户已 AC 题目数（distinct problem_id）
    solved_problems = (
        await db.execute(
            select(func.count(func.distinct(UserProblemAC.problem_id))).where(UserProblemAC.user_id == user_id)
        )
    ).scalar_one()

    # 5. 通过率 = 已 AC / 已发布总数（0-1 浮点，前端展示时 *100）
    acceptance_rate = solved_problems / total_problems if total_problems > 0 else 0.0

    # 6. 雷达图：各知识点 mastery（0-100）
    mastery_by_category = await _build_mastery_by_category(db, user_id)

    # 7. 薄弱知识点 ID 列表（0 < mastery < 0.5，严格按 spec）
    weak_ids = await _collect_weak_knowledge_ids(db, user_id)

    # 8. 训练目标完成进度
    target_progress = await _build_target_progress(db, user_id)

    # 9. 连续打卡天数（基于 Submission 自然日记录）
    streak_days = await _compute_streak_days(db, user_id)

    # 10. CF Rating 曲线（基于 RatingHistory）
    rating_history = await _build_rating_history(db, user_id)

    wrong_answers = (
        await db.execute(select(func.count(WrongBookEntry.id)).where(WrongBookEntry.user_id == user_id))
    ).scalar_one()
    unresolved_wrong_answers = (
        await db.execute(
            select(func.count(WrongBookEntry.id)).where(
                WrongBookEntry.user_id == user_id,
                WrongBookEntry.resolved.is_(False),
            )
        )
    ).scalar_one()

    return ProgressOverviewResponse(
        user_id=user_id,
        total_knowledge_points=total_kp,
        mastered_knowledge_points=mastered_kp,
        total_problems=total_problems,
        solved_problems=solved_problems,
        acceptance_rate=acceptance_rate,
        streak_days=streak_days,
        mastery_by_category=mastery_by_category,
        rating_history=rating_history,
        target_progress=target_progress,
        weak_knowledge_ids=weak_ids,
        wrong_answers=wrong_answers,
        unresolved_wrong_answers=unresolved_wrong_answers,
    )


async def _compute_streak_days(db: AsyncSession, user_id: UUID) -> int:
    """计算连续打卡天数（按用户时区 Asia/Shanghai 的自然日）。

    定义：用户最近一次提交的日期到今天，连续每天都有提交的天数。
    如果今天有提交且昨天也有，则 streak 至少为 2。
    如果最近一次提交是今天，streak = 1 + 连续昨天/前天...
    如果最近一次提交不是今天，streak = 0（断签）。
    无任何提交时返回 0。

    时区处理：
    - 数据库存储 UTC 时间，但用户时区是 Asia/Shanghai
    - 必须按用户时区转换后再计算自然日，否则北京时间 00:00-08:00 的提交
      会因为 UTC 仍是前一天而错误地断签
    """
    # 查询用户所有提交时间戳（UTC）
    rows = (
        await db.execute(
            select(Submission.submitted_at)
            .where(Submission.user_id == user_id)
            .order_by(Submission.submitted_at.desc())
        )
    ).all()
    if not rows:
        return 0

    # 按用户时区转换为自然日并去重
    from datetime import date, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.USER_TIMEZONE)
    days: set[date] = set()
    for row in rows:
        ts = row.submitted_at
        # 确保 ts 有时区信息（数据库可能返回 naive datetime）
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        days.add(ts.astimezone(tz).date())

    today = datetime.now(tz).date()
    # 第一条是最近一次提交日
    last_day = max(days)
    # 如果最近提交不是今天，streak = 0（断签）
    if last_day != today:
        return 0

    streak = 1
    for i in range(1, len(days)):
        expected = today - timedelta(days=i)
        if expected in days:
            streak += 1
        else:
            break
    return streak


async def _build_rating_history(db: AsyncSession, user_id: UUID) -> list[RatingHistoryPoint]:
    """构建 CF Rating 曲线。

    从 RatingHistory 表读取，按 rated_at 升序。
    无记录时返回空列表（不报错）。
    """
    rows = (
        (
            await db.execute(
                select(RatingHistory).where(RatingHistory.user_id == user_id).order_by(RatingHistory.rated_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        RatingHistoryPoint(
            date=row.rated_at.strftime("%Y-%m-%d"),
            rating=row.new_rating,
        )
        for row in rows
    ]


async def _count_mastered_knowledge(db: AsyncSession, user_id: UUID) -> int:
    """统计已掌握知识点数。

    spec: mastery >= 0.8 且 AC >= 3 且非 weak。
    不能只看 UserKnowledgeState.mastery，必须同时校验 AC 数。
    """
    # 加载用户所有非 weak 且 mastery >= 0.8 的知识点
    states = (
        (
            await db.execute(
                select(UserKnowledgeState.knowledge_id).where(
                    UserKnowledgeState.user_id == user_id,
                    UserKnowledgeState.mastery >= MASTERY_THRESHOLD,
                    UserKnowledgeState.is_weak.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )

    if not states:
        return 0

    mastered = 0
    for kid in states:
        ac_count = await _count_distinct_ac_in_knowledge(db, user_id, kid)
        if ac_count >= MASTERED_MIN_AC_COUNT:
            mastered += 1
    return mastered


async def _collect_weak_knowledge_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """收集薄弱知识点 ID（0 < mastery < 0.5）。

    spec: 0 < mastery < 0.5 为薄弱。
    mastery=0（未学）不算薄弱。
    """
    rows = (
        (
            await db.execute(
                select(UserKnowledgeState.knowledge_id).where(
                    UserKnowledgeState.user_id == user_id,
                    UserKnowledgeState.is_weak.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _build_mastery_by_category(db: AsyncSession, user_id: UUID) -> list[MasteryByCategory]:
    """构造雷达图数据：每个知识点的 mastery 百分比 + knowledge_id。

    对于用户尚未有 UserKnowledgeState 记录的知识点，mastery 视为 0。
    返回 knowledge_id 用于前端映射 weak_knowledge_ids。
    """
    kps = (
        await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name).order_by(KnowledgePoint.order, KnowledgePoint.name)
        )
    ).all()

    states = (
        await db.execute(
            select(UserKnowledgeState.knowledge_id, UserKnowledgeState.mastery).where(
                UserKnowledgeState.user_id == user_id
            )
        )
    ).all()
    mastery_map = {s.knowledge_id: s.mastery for s in states}

    result: list[MasteryByCategory] = []
    for kp_id, kp_name in kps:
        m = mastery_map.get(kp_id, 0.0)
        result.append(
            MasteryByCategory(
                knowledge_id=kp_id,
                name=kp_name,
                value=int(m * 100),
            )
        )
    return result


async def _build_target_progress(db: AsyncSession, user_id: UUID) -> TargetProgress | None:
    """构造训练目标完成进度。"""
    profile = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalar_one_or_none()
    if profile is None:
        return None

    # COMPAT: KnowledgePoint 无 rating 字段，用全部知识点作为分母
    total_kp = (await db.execute(select(func.count(KnowledgePoint.id)))).scalar_one()
    mastered_in_range = await _count_mastered_knowledge(db, user_id)

    progress_percent = int(mastered_in_range / total_kp * 100) if total_kp > 0 else 0

    return TargetProgress(
        target_rating_min=profile.target_rating_min,
        target_rating_max=profile.target_rating_max,
        mastered_in_range=mastered_in_range,
        total_in_range=total_kp,
        progress_percent=progress_percent,
    )


async def recompute_mastery(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID | None = None,
) -> RecomputeMasteryResponse:
    """重算 mastery = AC 题数 / 该知识点关联已发布题目总数。

    Args:
        user_id: 用户 ID
        knowledge_id: 指定知识点；None 时重算用户全量知识点（包括有 state
            和有 AC 数据但无 state 的知识点）

    返回：
        recomputed: 本次重算的知识点数量
        updated: mastery 或 is_weak 实际发生变化的知识点数量
    """
    if knowledge_id is not None:
        # 校验知识点存在，避免外键错误变成 500
        exists = (
            await db.execute(select(KnowledgePoint.id).where(KnowledgePoint.id == knowledge_id))
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(f"knowledge_id {knowledge_id} not found")
        target_ids = [knowledge_id]
    else:
        target_ids = await _collect_user_knowledge_ids(db, user_id)

    if not target_ids:
        return RecomputeMasteryResponse(user_id=user_id, recomputed=0, updated=0)

    recomputed = 0
    updated = 0
    for kid in target_ids:
        old_mastery, old_weak = await _load_state(db, user_id, kid)
        new_mastery = await _compute_mastery_for_knowledge(db, user_id, kid)

        # 即使 mastery 数值没变，也可能需要修正错误的 is_weak
        new_weak = _classify_weak(new_mastery, old_weak)
        if new_mastery != old_mastery or new_weak != old_weak:
            await _upsert_state(db, user_id, kid, new_mastery, new_weak)
            updated += 1
        recomputed += 1

    await db.flush()
    return RecomputeMasteryResponse(user_id=user_id, recomputed=recomputed, updated=updated)


async def _collect_user_knowledge_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """收集用户所有需要重算的知识点 ID（去重）。

    覆盖：
    - 用户已有 UserKnowledgeState 的知识点
    - 用户已 AC 题目通过 ProblemKnowledgePoint 关联到的知识点
    """
    state_ids = (
        (await db.execute(select(UserKnowledgeState.knowledge_id).where(UserKnowledgeState.user_id == user_id)))
        .scalars()
        .all()
    )

    ac_kp_ids = (
        (
            await db.execute(
                select(ProblemKnowledgePoint.knowledge_id)
                .join(UserProblemAC, UserProblemAC.problem_id == ProblemKnowledgePoint.problem_id)
                .where(UserProblemAC.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )

    return list(set(state_ids) | set(ac_kp_ids))


async def recompute_mastery_for_knowledge(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> float:
    """重算单个知识点的 mastery 并写入 UserKnowledgeState。

    供 Task 10 的 record_attempt(AC) 调用，实现 AC 时自动重算。
    返回更新后的 mastery 值。
    """
    new_mastery = await _compute_mastery_for_knowledge(db, user_id, knowledge_id)
    old_mastery, old_weak = await _load_state(db, user_id, knowledge_id)
    new_weak = _classify_weak(new_mastery, old_weak)
    if new_mastery != old_mastery or new_weak != old_weak:
        await _upsert_state(db, user_id, knowledge_id, new_mastery, new_weak)
        await db.flush()
    return new_mastery


def _classify_weak(mastery: float, old_weak: bool) -> bool:
    """根据 mastery 严格按 spec 分类 is_weak。

    spec:
    - 0 < mastery < 0.5 → weak = True
    - mastery >= 0.8 → weak = False
    - mastery == 0（未学）→ weak = False（不是薄弱）
    - 0.5 <= mastery < 0.8 → 保持原状态
    """
    if mastery <= 0.0:
        return False
    if mastery < WEAK_MASTERY_THRESHOLD:
        return True
    if mastery >= MASTERY_THRESHOLD:
        return False
    return old_weak


async def _compute_mastery_for_knowledge(db: AsyncSession, user_id: UUID, knowledge_id: UUID) -> float:
    """计算单个知识点的 mastery。

    mastery = 用户在该知识点已 AC 的已发布题目数 / 该知识点关联的已发布题目总数

    严格规则：
    - 分子和分母必须使用完全一致的题目集合（published 且通过 ProblemKnowledgePoint 关联）
    - 使用 distinct problem_id 计数
    - mastery 限制在 0~1
    - draft 题目、无关知识点题目不得进入分子
    """
    # 该知识点关联的已发布题目总数（分母）
    total = (
        await db.execute(
            select(func.count(func.distinct(ProblemKnowledgePoint.problem_id)))
            .join(Problem, Problem.id == ProblemKnowledgePoint.problem_id)
            .where(
                ProblemKnowledgePoint.knowledge_id == knowledge_id,
                Problem.status == ProblemStatus.PUBLISHED,
            )
        )
    ).scalar_one()

    if total == 0:
        return 0.0

    # 用户在该知识点已 AC 的已发布题目数（分子，与分母同集合）
    ac_count = await _count_distinct_ac_in_knowledge(db, user_id, knowledge_id)

    mastery = ac_count / total
    # 防御性：mastery 必须在 0~1 之间
    return max(0.0, min(1.0, mastery))


async def _count_distinct_ac_in_knowledge(db: AsyncSession, user_id: UUID, knowledge_id: UUID) -> int:
    """统计用户在某知识点已 AC 的已发布题目数（distinct problem_id）。

    严格过滤：必须通过 ProblemKnowledgePoint 关联到指定知识点，
    且 Problem.status == published，且在 UserProblemAC 中有记录。
    """
    return (
        await db.execute(
            select(func.count(func.distinct(UserProblemAC.problem_id)))
            .join(ProblemKnowledgePoint, ProblemKnowledgePoint.problem_id == UserProblemAC.problem_id)
            .join(Problem, Problem.id == UserProblemAC.problem_id)
            .where(
                UserProblemAC.user_id == user_id,
                ProblemKnowledgePoint.knowledge_id == knowledge_id,
                Problem.status == ProblemStatus.PUBLISHED,
            )
        )
    ).scalar_one()


async def _load_state(db: AsyncSession, user_id: UUID, knowledge_id: UUID) -> tuple[float, bool]:
    """加载现有 UserKnowledgeState 的 (mastery, is_weak)。若无记录返回 (0.0, False)。"""
    state = (
        await db.execute(
            select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == knowledge_id,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        return 0.0, False
    return state.mastery, state.is_weak


async def _upsert_state(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
    mastery: float,
    new_weak: bool,
) -> None:
    """写入或更新 UserKnowledgeState。

    注意：调用方应先用 _classify_weak 计算 new_weak，这里直接写入。
    """
    state = (
        await db.execute(
            select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == knowledge_id,
            )
        )
    ).scalar_one_or_none()

    if state is None:
        db.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=knowledge_id,
                mastery=mastery,
                is_weak=new_weak,
                consecutive_wa=0,
            )
        )
    else:
        state.mastery = mastery
        state.is_weak = new_weak
