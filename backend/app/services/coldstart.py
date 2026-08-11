"""水平测试与冷启动 service (Task 9)。

覆盖：
- 9.1 CF 冷启动：拉 user.status → cf_tags 映射 → mastery 计算 → 训练目标
- 9.2 诊断题冷启动：选 15 题覆盖 10 核心知识点
- 9.3 起点定标：已掌握最远后代 / 薄弱节点 / 下一可学节点
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import CodeforcesAccount
from app.models.knowledge import KnowledgePoint
from app.models.learning import (
    MASTERY_THRESHOLD,
    LearningProfile,
    UserKnowledgeState,
)
from app.models.problem import Problem, ProblemDifficulty, ProblemKnowledgePoint, ProblemSource, ProblemStatus

logger = logging.getLogger(__name__)


# ===== 9.1 CF 冷启动 =====

# CF tag → 知识点 slug 映射（简化版，覆盖常见 tag）
CF_TAG_TO_KNOWLEDGE_SLUG: dict[str, str] = {
    "dp": "dynamic-programming",
    "greedy": "greedy",
    "binary search": "binary-search",
    "two pointers": "two-pointers",
    "data structures": "data-structures",
    "graphs": "graph-theory",
    "dfs and similar": "dfs",
    "bfs": "bfs",
    "trees": "trees",
    "strings": "strings",
    "math": "math",
    "number theory": "number-theory",
    "combinatorics": "combinatorics",
    "geometry": "geometry",
    "sortings": "sorting",
    "constructive algorithms": "constructive",
    "implementation": "implementation",
    "bitmasks": "bitmasks",
    "divide and conquer": "divide-and-conquer",
    "shortest paths": "shortest-paths",
    "dsu": "dsu",
    "flows": "flows",
    "hashing": "hashing",
    "probabilities": "probabilities",
    "games": "game-theory",
}


@dataclass
class ColdStartResult:
    """冷启动结果。"""

    user_id: UUID
    method: str  # "codeforces" | "diagnostic"
    # 训练目标
    target_rating_min: int
    target_rating_max: int
    # 已掌握知识点数
    mastered_count: int
    # 薄弱知识点数
    weak_count: int
    # 下一可学知识点数
    next_available_count: int
    # 诊断题列表（仅 diagnostic 方法）
    diagnostic_problems: list[UUID] = field(default_factory=list)


async def cf_cold_start(
    db: AsyncSession,
    user_id: UUID,
    cf_client=None,
) -> ColdStartResult:
    """CF 冷启动：拉取 user.status，映射到知识点，计算 mastery。

    仅当用户在 CF 有 ≥ 20 条提交记录时走此路径。
    否则返回不充分的 cold start 结果（前端应提示走诊断题路径）。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        cf_client: CodeforcesClient 实例（可选）

    Returns:
        ColdStartResult: 冷启动结果
    """
    from app.services.codeforces.client import (
        close_codeforces_client,
        get_codeforces_client,
    )

    # 获取 CF account
    account = (
        await db.execute(select(CodeforcesAccount).where(CodeforcesAccount.user_id == user_id))
    ).scalar_one_or_none()

    if account is None:
        return ColdStartResult(
            user_id=user_id,
            method="codeforces",
            target_rating_min=1200,
            target_rating_max=1600,
            mastered_count=0,
            weak_count=0,
            next_available_count=0,
        )

    # 拉取 user.status
    should_close = False
    if cf_client is None:
        cf_client = get_codeforces_client()
        should_close = True

    try:
        submissions = await cf_client.user_status(account.handle, count=100)
    finally:
        if should_close:
            await close_codeforces_client(cf_client)

    if len(submissions) < 20:
        return ColdStartResult(
            user_id=user_id,
            method="codeforces",
            target_rating_min=1200,
            target_rating_max=1600,
            mastered_count=0,
            weak_count=0,
            next_available_count=0,
        )

    # 映射 CF tags → 知识点
    tag_kp_map = await _build_cf_tag_knowledge_map(db)
    # 按知识点聚合 AC / 提交数
    kp_ac: dict[UUID, int] = defaultdict(int)
    kp_total: dict[UUID, int] = defaultdict(int)

    for sub in submissions:
        problem = sub.get("problem", {})
        tags = problem.get("tags", [])
        verdict = sub.get("verdict", "")
        is_ac = verdict == "OK"

        for tag in tags:
            kp_id = tag_kp_map.get(tag.lower())
            if kp_id is None:
                continue
            kp_total[kp_id] += 1
            if is_ac:
                kp_ac[kp_id] += 1

    # 计算 mastery 并写入 UserKnowledgeState
    for kp_id in kp_total:
        mastery = kp_ac[kp_id] / kp_total[kp_id] if kp_total[kp_id] > 0 else 0.0
        mastery = min(1.0, max(0.0, mastery))
        is_weak = 0.0 < mastery < 0.5
        await _upsert_knowledge_state(db, user_id, kp_id, mastery, is_weak)

    await db.flush()

    # 设置训练目标
    rating = account.current_rating or 1200
    target_min, target_max = _rating_to_target(rating)
    await _set_learning_profile(db, user_id, target_min, target_max)

    # 起点定标
    calibration = await _calibrate_starting_point(db, user_id)

    return ColdStartResult(
        user_id=user_id,
        method="codeforces",
        target_rating_min=target_min,
        target_rating_max=target_max,
        mastered_count=calibration.mastered_count,
        weak_count=calibration.weak_count,
        next_available_count=calibration.next_available_count,
    )


# ===== 9.2 诊断题冷启动 =====


async def diagnostic_cold_start(
    db: AsyncSession,
    user_id: UUID,
) -> ColdStartResult:
    """诊断题冷启动：从自建题库选 15 题覆盖 10 核心知识点。

    选题规则：
    - 仅选 source=platform 的已发布题目
    - 5 易 + 7 中 + 3 难
    - 覆盖 10 个不同知识点
    """
    # 取 10 个核心知识点（按 order 排序）
    core_kps = (
        (await db.execute(select(KnowledgePoint.id).order_by(KnowledgePoint.order, KnowledgePoint.name).limit(10)))
        .scalars()
        .all()
    )

    if not core_kps:
        return ColdStartResult(
            user_id=user_id,
            method="diagnostic",
            target_rating_min=1200,
            target_rating_max=1600,
            mastered_count=0,
            weak_count=0,
            next_available_count=0,
        )

    diagnostic_problems: list[UUID] = []

    # 选 5 easy 题
    easy_problems = await _pick_problems_by_difficulty(db, core_kps, ProblemDifficulty.EASY, 5, diagnostic_problems)
    diagnostic_problems.extend(easy_problems)

    # 选 7 medium 题
    medium_problems = await _pick_problems_by_difficulty(db, core_kps, ProblemDifficulty.MEDIUM, 7, diagnostic_problems)
    diagnostic_problems.extend(medium_problems)

    # 选 3 hard 题
    hard_problems = await _pick_problems_by_difficulty(db, core_kps, ProblemDifficulty.HARD, 3, diagnostic_problems)
    diagnostic_problems.extend(hard_problems)

    # 设置默认训练目标
    await _set_learning_profile(db, user_id, 1200, 1600)

    return ColdStartResult(
        user_id=user_id,
        method="diagnostic",
        target_rating_min=1200,
        target_rating_max=1600,
        mastered_count=0,
        weak_count=0,
        next_available_count=len(core_kps),
        diagnostic_problems=diagnostic_problems,
    )


# ===== 9.3 起点定标 =====


@dataclass
class CalibrationResult:
    """起点定标结果。"""

    mastered_count: int
    weak_count: int
    next_available_count: int
    weak_knowledge_ids: list[UUID] = field(default_factory=list)
    next_knowledge_ids: list[UUID] = field(default_factory=list)


async def _calibrate_starting_point(
    db: AsyncSession,
    user_id: UUID,
) -> CalibrationResult:
    """起点定标：识别已掌握、薄弱、下一可学节点。

    算法：
    - 已掌握：mastery ≥ 0.8 且非 weak
    - 薄弱：0 < mastery < 0.5
    - 下一可学：前置已满足（所有前置都在已掌握或已学集合中）且未掌握
    """
    from app.models.knowledge import KnowledgePrerequisite

    states = (await db.execute(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id))).scalars().all()
    state_map = {s.knowledge_id: s for s in states}

    # 已掌握
    mastered_ids: set[UUID] = set()
    for s in states:
        if s.mastery >= MASTERY_THRESHOLD and not s.is_weak:
            mastered_ids.add(s.knowledge_id)

    # 薄弱
    weak_ids: list[UUID] = []
    for s in states:
        if 0.0 < s.mastery < 0.5:
            weak_ids.append(s.knowledge_id)

    # 加载所有前置依赖
    edges = (await db.execute(select(KnowledgePrerequisite))).scalars().all()
    prereq_map: dict[UUID, list[UUID]] = defaultdict(list)
    for e in edges:
        prereq_map[e.knowledge_id].append(e.prerequisite_id)

    # 所有有状态的知识点（已学）
    learned_ids = set(state_map.keys())

    # 下一可学：前置都在 learned_ids ∪ mastered_ids 中，且未掌握
    kps = (await db.execute(select(KnowledgePoint.id))).scalars().all()
    next_ids: list[UUID] = []
    for kp_id in kps:
        if kp_id in mastered_ids:
            continue
        prereqs = prereq_map.get(kp_id, [])
        if all(p in learned_ids or p in mastered_ids for p in prereqs):
            next_ids.append(kp_id)

    return CalibrationResult(
        mastered_count=len(mastered_ids),
        weak_count=len(weak_ids),
        next_available_count=len(next_ids),
        weak_knowledge_ids=weak_ids,
        next_knowledge_ids=next_ids[:10],
    )


# ===== 辅助函数 =====


async def _build_cf_tag_knowledge_map(db: AsyncSession) -> dict[str, UUID]:
    """构建 CF tag → 知识点 ID 映射。"""
    kps = (await db.execute(select(KnowledgePoint.id, KnowledgePoint.slug))).all()
    # 按 slug 全词匹配 CF tag 映射
    slug_to_id = {kp.slug: kp.id for kp in kps if kp.slug}

    tag_to_id: dict[str, UUID] = {}
    for tag, slug in CF_TAG_TO_KNOWLEDGE_SLUG.items():
        kp_id = slug_to_id.get(slug)
        if kp_id is not None:
            tag_to_id[tag] = kp_id
    return tag_to_id


async def _upsert_knowledge_state(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
    mastery: float,
    is_weak: bool,
) -> None:
    """写入或更新 UserKnowledgeState。"""
    existing = (
        await db.execute(
            select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == knowledge_id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        db.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=knowledge_id,
                mastery=mastery,
                is_weak=is_weak,
                consecutive_wa=0,
            )
        )
    else:
        existing.mastery = mastery
        existing.is_weak = is_weak


def _rating_to_target(rating: int) -> tuple[int, int]:
    """按 CF Rating 定训练目标。

    spec:
    - <1200 铜牌向
    - 1200-1600 银牌向
    - 1600-2000 金牌向
    - >2000 高级向
    """
    if rating < 1200:
        return (800, 1200)
    if rating < 1600:
        return (1200, 1600)
    if rating < 2000:
        return (1600, 2000)
    return (2000, 2600)


async def _set_learning_profile(
    db: AsyncSession,
    user_id: UUID,
    target_min: int,
    target_max: int,
) -> None:
    """设置用户训练目标。"""
    existing = (
        await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            LearningProfile(
                user_id=user_id,
                target_rating_min=target_min,
                target_rating_max=target_max,
            )
        )
    else:
        existing.target_rating_min = target_min
        existing.target_rating_max = target_max
    await db.flush()


async def _pick_problems_by_difficulty(
    db: AsyncSession,
    knowledge_ids: list[UUID],
    difficulty: ProblemDifficulty,
    count: int,
    exclude_ids: list[UUID],
) -> list[UUID]:
    """从自建题库中选题，按难度筛选，已选题自动排除。"""
    exclude_set = set(exclude_ids)
    result: list[UUID] = []

    for kp_id in knowledge_ids:
        if len(result) >= count:
            break
        rows = (
            (
                await db.execute(
                    select(Problem.id)
                    .join(ProblemKnowledgePoint, ProblemKnowledgePoint.problem_id == Problem.id)
                    .where(
                        ProblemKnowledgePoint.knowledge_id == kp_id,
                        Problem.source == ProblemSource.PLATFORM,
                        Problem.status == ProblemStatus.PUBLISHED,
                        Problem.difficulty == difficulty,
                    )
                    .limit(count)
                )
            )
            .scalars()
            .all()
        )
        for pid in rows:
            if pid not in exclude_set and len(result) < count:
                result.append(pid)
                exclude_set.add(pid)

    return result
