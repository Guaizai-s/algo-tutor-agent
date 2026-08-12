"""题目推荐查询逻辑 service (Task 10.4)。

核心规则：
- 通过 ProblemKnowledgePoint 限定知识点
- 仅查询 published 问题
- 排除该用户已 AC 的题目
- 按 cf_rating ASC 排序，相同 rating 按 created_at, title 稳定次级排序
- 正确处理 cf_rating IS NULL：未定级题不混入依赖 rating 区间的槽位
- 候选不足时自动降级到子知识点（递归收集所有后代）
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge import KnowledgePoint
from app.models.learning import LearningProfile, UserProblemAC
from app.models.problem import Problem, ProblemKnowledgePoint, ProblemStatus


async def _load_ac_problem_ids(db: AsyncSession, user_id: UUID) -> set[UUID]:
    """加载用户已 AC 的题目 id 集合。"""
    rows = (await db.execute(select(UserProblemAC.problem_id).where(UserProblemAC.user_id == user_id))).scalars().all()
    return set(rows)


async def _load_or_create_profile(db: AsyncSession, user_id: UUID) -> LearningProfile:
    """加载或创建用户学习画像（默认 1200-1600 银牌向）。"""
    profile = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalar_one_or_none()
    if profile is None:
        profile = LearningProfile(
            user_id=user_id,
            target_rating_min=1200,
            target_rating_max=1600,
        )
        db.add(profile)
        await db.flush()
    return profile


async def _collect_descendant_kp_ids(db: AsyncSession, root_id: UUID) -> list[UUID]:
    """递归收集某知识点的所有后代知识点 ID（含自身）。

    通过 parent_id 字段递归查找，用于候选不足时扩大搜索范围。
    """
    all_kps = (await db.execute(select(KnowledgePoint.id, KnowledgePoint.parent_id))).all()
    # 构建 parent_id -> [child_id] 映射
    children_map: dict[UUID, list[UUID]] = {}
    for kp_id, parent_id in all_kps:
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(kp_id)

    result: list[UUID] = [root_id]
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child_id in children_map.get(current, []):
            result.append(child_id)
            stack.append(child_id)
    return result


async def recommend_problems_by_knowledge(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
    rating_min: float | None = None,
    rating_max: float | None = None,
    limit: int = 10,
    exclude_ac: bool = True,
    require_rating: bool = False,
    expand_descendants: bool = False,
) -> list[Problem]:
    """按知识点查询推荐题目。

    Args:
        knowledge_id: 必须通过 ProblemKnowledgePoint 关联
        rating_min: cf_rating 下限（含）；None 表示不限
        rating_max: cf_rating 上限（含）；None 表示不限
        limit: 最多返回数量
        exclude_ac: 是否排除已 AC 题目
        require_rating: True 时仅返回 cf_rating NOT NULL 的题（用于 rating 槽位）
        expand_descendants: True 时同时搜索该知识点所有后代知识点
    """
    ac_ids = await _load_ac_problem_ids(db, user_id) if exclude_ac else set()

    if expand_descendants:
        kp_ids = await _collect_descendant_kp_ids(db, knowledge_id)
    else:
        kp_ids = [knowledge_id]

    stmt = (
        select(Problem)
        .join(ProblemKnowledgePoint, ProblemKnowledgePoint.problem_id == Problem.id)
        .where(
            ProblemKnowledgePoint.knowledge_id.in_(kp_ids),
            Problem.status == ProblemStatus.PUBLISHED,
        )
        .options(selectinload(Problem.knowledge_points))
    )
    if rating_min is not None:
        stmt = stmt.where(Problem.cf_rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(Problem.cf_rating <= rating_max)
    if require_rating:
        stmt = stmt.where(Problem.cf_rating.is_not(None))
    if ac_ids:
        stmt = stmt.where(Problem.id.notin_(ac_ids))

    # 按 cf_rating ASC, 相同 rating 按 created_at ASC, title ASC 稳定排序
    stmt = stmt.order_by(
        Problem.cf_rating.asc(),
        Problem.created_at.asc(),
        Problem.title.asc(),
    ).limit(limit)

    return list((await db.execute(stmt)).scalars().all())


async def recommend_for_slots(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> tuple[
    list[Problem],
    list[Problem],
    list[Problem],
    list[Problem],
    LearningProfile,
]:
    """为当日任务四个槽位查询候选题。

    返回 (template_candidates, application_candidates, challenge_candidates, no_rating_candidates, profile)：
    - template: cf_rating <= target_min
    - application: target_min <= cf_rating <= target_max
    - challenge: cf_rating >= target_max
    - no_rating: cf_rating IS NULL（用于 fallback）

    当目标知识点候选不足时，自动降级到子知识点搜索。
    """
    profile = await _load_or_create_profile(db, user_id)
    tmin = float(profile.target_rating_min)
    tmax = float(profile.target_rating_max)

    template = await recommend_problems_by_knowledge(
        db,
        user_id,
        knowledge_id,
        rating_max=tmin,
        limit=5,
        require_rating=True,
        expand_descendants=True,
    )
    application = await recommend_problems_by_knowledge(
        db,
        user_id,
        knowledge_id,
        rating_min=tmin,
        rating_max=tmax,
        limit=5,
        require_rating=True,
        expand_descendants=True,
    )
    challenge = await recommend_problems_by_knowledge(
        db,
        user_id,
        knowledge_id,
        rating_min=tmax,
        limit=5,
        require_rating=True,
        expand_descendants=True,
    )
    no_rating = await recommend_problems_by_knowledge(
        db,
        user_id,
        knowledge_id,
        limit=10,
        require_rating=False,
        expand_descendants=True,
    )
    # no_rating 查询本身不过滤 require_rating，需手动取 IS NULL 的子集
    no_rating = [p for p in no_rating if p.cf_rating is None]

    return template, application, challenge, no_rating, profile
