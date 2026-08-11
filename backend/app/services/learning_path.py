"""学习路径生成与动态调整 service (Task 10.1 + 10.2)。

核心逻辑：
- 基于 KnowledgePrerequisite 构建知识点 DAG
- 确定性拓扑排序（Kahn 算法 + tie-break by KnowledgePoint.order/name）
- 环检测：抛领域错误 CycleDetectedError
- 已掌握节点（mastery ≥ 0.8 且非 weak）跳过
- weak / remediation 节点保留
- 未掌握但前置未满足的节点标记为 pending（不进入 active 预览）
- 连续 WA 3 次触发补漏插入
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge import CodeTemplate, KnowledgePoint, KnowledgePrerequisite, Lecture
from app.models.learning import (
    CONSECUTIVE_WA_THRESHOLD,
    MASTERY_THRESHOLD,
    LearningPath,
    LearningPathItem,
    PathItemKind,
    PathItemStatus,
    UserKnowledgeState,
)
from app.schemas.learning import (
    AttemptResponse,
    KnowledgePointRef,
    LearningPathItemRead,
    LearningPathRead,
    RoadmapKnowledgeNode,
    RoadmapResponse,
)

logger = logging.getLogger(__name__)


class CycleDetectedError(Exception):
    """知识点 DAG 中检测到环。"""

    def __init__(self, cycle_nodes: list[UUID]) -> None:
        self.cycle_nodes = cycle_nodes
        super().__init__(f"knowledge prerequisite graph has a cycle: {cycle_nodes}")


# ===== 10.1 路径生成 =====


async def _load_dag(db: AsyncSession) -> tuple[dict[UUID, KnowledgePoint], dict[UUID, list[UUID]]]:
    """加载所有知识点与前置依赖边。

    Returns:
        (kp_map, adj) 其中
          kp_map: knowledge_id -> KnowledgePoint
          adj: prerequisite_id -> [knowledge_id]（前置指向后继）
    """
    kps = (await db.execute(select(KnowledgePoint))).scalars().all()
    kp_map = {kp.id: kp for kp in kps}

    edges = (await db.execute(select(KnowledgePrerequisite))).scalars().all()
    adj: dict[UUID, list[UUID]] = defaultdict(list)
    for e in edges:
        adj[e.prerequisite_id].append(e.knowledge_id)
    return kp_map, adj


def topological_sort(
    kp_map: dict[UUID, KnowledgePoint],
    adj: dict[UUID, list[UUID]],
) -> list[UUID]:
    """确定性拓扑排序（Kahn 算法）。

    - 入度 0 的节点先出
    - 同层节点按 KnowledgePoint.order, KnowledgePoint.name 稳定排序
    - 检测到环时抛 CycleDetectedError
    """
    indeg: dict[UUID, int] = {kid: 0 for kid in kp_map}
    for src, dsts in adj.items():
        for d in dsts:
            indeg[d] = indeg.get(d, 0) + 1

    # 初始队列：入度为 0 的节点，按 order/name 排序保证确定性
    def _sort_key(kid: UUID) -> tuple[int, str]:
        kp = kp_map[kid]
        return (kp.order, kp.name)

    queue: deque[UUID] = deque(sorted([k for k, d in indeg.items() if d == 0], key=_sort_key))
    result: list[UUID] = []

    while queue:
        n = queue.popleft()
        result.append(n)
        # 邻接后继
        nexts = sorted(adj.get(n, []), key=_sort_key)
        for m in nexts:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
        # 重新排序队列以保持确定性（Kahn + 优先队列的等价实现）
        # 为保持简单且稳定，这里重新排序
        queue = deque(sorted(queue, key=_sort_key))

    if len(result) != len(kp_map):
        remaining = [k for k in kp_map if k not in set(result)]
        raise CycleDetectedError(remaining)

    return result


async def _load_user_states(db: AsyncSession, user_id: UUID) -> dict[UUID, UserKnowledgeState]:
    """加载用户所有知识点状态。"""
    rows = (await db.execute(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id))).scalars().all()
    return {r.knowledge_id: r for r in rows}


async def generate_learning_path(
    db: AsyncSession,
    user_id: UUID,
    preview_count: int = 8,
) -> LearningPathRead:
    """生成用户学习路径并持久化。

    规则：
    - 拓扑排序后过滤掉已掌握节点（mastery ≥ 0.8 且非 weak）
    - weak / remediation 节点必须保留
    - 未掌握但前置未满足的节点保留在路径中（status=pending）
    - 预览取前 preview_count 个，不足时返回实际数量
    - 重新生成时将旧路径标记为 archived
    """
    kp_map, adj = await _load_dag(db)
    topo = topological_sort(kp_map, adj)
    user_states = await _load_user_states(db, user_id)

    # 计算每个节点的"前置是否全部已掌握"（用于判断 active vs pending）
    mastered_set: set[UUID] = set()
    for kid, st in user_states.items():
        if st.mastery >= MASTERY_THRESHOLD and not st.is_weak:
            mastered_set.add(kid)

    # 构建入度反向索引：knowledge_id -> [prerequisite_id]
    prereq_map: dict[UUID, list[UUID]] = defaultdict(list)
    for src, dsts in adj.items():
        for d in dsts:
            prereq_map[d].append(src)

    items_to_add: list[tuple[UUID, PathItemKind, PathItemStatus]] = []
    for kid in topo:
        st = user_states.get(kid)
        # 已掌握跳过
        if st and st.mastery >= MASTERY_THRESHOLD and not st.is_weak:
            continue
        # weak 节点保留为 remediation
        if st and st.is_weak:
            kind = PathItemKind.REMEDIATION
        else:
            kind = PathItemKind.NORMAL
        # 判断前置是否满足
        prereqs = prereq_map.get(kid, [])
        prereq_satisfied = all(p in mastered_set for p in prereqs)
        status = PathItemStatus.ACTIVE if prereq_satisfied else PathItemStatus.PENDING
        items_to_add.append((kid, kind, status))

    # 截取预览数量（不复制节点凑数）
    preview = items_to_add[:preview_count]

    # 归档旧路径
    await db.execute(update(LearningPath).where(LearningPath.user_id == user_id).values(is_active=False))

    path = LearningPath(user_id=user_id, is_active=True)
    db.add(path)
    try:
        await db.flush()  # 拿到 path.id
    except IntegrityError:
        # 并发场景：另一个请求已先创建了 active 路径（部分唯一索引拦截）。
        # 回滚本次事务后读取已存在的 active 路径返回。
        # 注意：必须 rollback，否则后续操作会因事务 aborted 而失败。
        await db.rollback()
        existing = await get_current_learning_path(db, user_id)
        if existing is not None:
            return existing
        raise

    for i, (kid, kind, status) in enumerate(preview):
        db.add(
            LearningPathItem(
                path_id=path.id,
                knowledge_id=kid,
                position=i,
                kind=kind,
                status=status,
            )
        )
    await db.flush()

    return await _build_path_read(db, path)


async def mark_knowledge_mastered(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> tuple[float, int]:
    """标记知识点为已掌握（自评），并跳过路径中对应项。

    - 将 UserKnowledgeState.mastery 设为 1.0，清除 is_weak
    - 将当前 active 路径中该知识点的项标记为 SKIPPED
    - 返回 (mastery, skipped_count)
    """
    # 1. Upsert UserKnowledgeState
    stmt = select(UserKnowledgeState).where(
        UserKnowledgeState.user_id == user_id,
        UserKnowledgeState.knowledge_id == knowledge_id,
    )
    state = (await db.execute(stmt)).scalar_one_or_none()
    if state is None:
        state = UserKnowledgeState(
            user_id=user_id,
            knowledge_id=knowledge_id,
            mastery=1.0,
            is_weak=False,
            consecutive_wa=0,
        )
        db.add(state)
    else:
        state.mastery = 1.0
        state.is_weak = False
        state.consecutive_wa = 0
    await db.flush()

    # 2. 标记当前 active 路径中对应项为 SKIPPED
    skipped = 0
    path_stmt = (
        select(LearningPath)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPath.items))
    )
    path = (await db.execute(path_stmt)).scalar_one_or_none()
    if path is not None:
        for item in path.items:
            if item.knowledge_id == knowledge_id and item.status != PathItemStatus.SKIPPED:
                item.status = PathItemStatus.SKIPPED
                skipped += 1
        if skipped > 0:
            await db.flush()
            # 解锁后续 pending 项
            await _unlock_pending_items(db, user_id)

    return 1.0, skipped


async def get_current_learning_path(db: AsyncSession, user_id: UUID) -> LearningPathRead | None:
    """读取用户当前 active 路径。若无则返回 None。"""
    stmt = (
        select(LearningPath)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPath.items).selectinload(LearningPathItem.knowledge))
    )
    path = (await db.execute(stmt)).scalar_one_or_none()
    if path is None:
        return None
    return await _build_path_read(db, path)


async def _build_path_read(db: AsyncSession, path: LearningPath) -> LearningPathRead:
    """构造 LearningPathRead 响应。"""
    # 重新查询以拿到 items + knowledge 关系（避免 lazy load）
    stmt = (
        select(LearningPathItem)
        .where(LearningPathItem.path_id == path.id)
        .options(selectinload(LearningPathItem.knowledge))
        .order_by(LearningPathItem.position)
    )
    items = (await db.execute(stmt)).scalars().all()
    return LearningPathRead(
        id=path.id,
        user_id=path.user_id,
        is_active=path.is_active,
        items=[
            LearningPathItemRead(
                id=it.id,
                knowledge_id=it.knowledge_id,
                position=it.position,
                kind=it.kind,
                status=it.status,
                knowledge=KnowledgePointRef(
                    id=it.knowledge.id,
                    name=it.knowledge.name,
                    slug=it.knowledge.slug,
                ),
            )
            for it in items
        ],
    )


# ===== 10.2 路径动态调整 =====


async def record_attempt(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
    problem_id: UUID,
    verdict: str,
    new_mastery: float | None = None,  # DEPRECATED: 服务端忽略，mastery 由 AC/总数 计算
) -> AttemptResponse:
    """记录一次做题结果并触发路径动态调整。

    spec: mastery 由服务端按 AC 题数 / 关联题目总数 计算，
    客户端传入的 new_mastery 被忽略（deprecated）。

    规则：
    - AC：重置 consecutive_wa=0；写入 UserProblemAC；按 AC/总数 重算 mastery；
      若 mastery ≥ 0.8 则清除 weak 并把对应路径项恢复为 normal；
      若 mastery ≥ 0.8 则把该知识点路径项标记为 DONE。
    - WA：consecutive_wa += 1；不改 mastery；
      - 仅当 consecutive_wa 达到 CONSECUTIVE_WA_THRESHOLD(=3) 时才标记 weak
        并插入/提升 remediation；
      - mastery 不作为 weak 触发条件（新用户 mastery=0.0 不应仅凭一次 WA
        就被误判为 weak）；
      - 重复 WA（第 4、5 次）不重复插入相同补漏项。
    """
    is_ac = verdict.upper() == "AC"

    # 1. 加载或创建 state
    stmt = select(UserKnowledgeState).where(
        UserKnowledgeState.user_id == user_id,
        UserKnowledgeState.knowledge_id == knowledge_id,
    )
    state = (await db.execute(stmt)).scalar_one_or_none()
    if state is None:
        state = UserKnowledgeState(
            user_id=user_id,
            knowledge_id=knowledge_id,
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
        db.add(state)
        await db.flush()

    remediation_inserted = False

    if is_ac:
        # 1) 记录 AC 到 UserProblemAC（业务闭环：推荐会排除已 AC 题目）
        await _record_problem_ac(db, user_id, problem_id)
        # 2) 重置连续 WA
        state.consecutive_wa = 0
        # 3) AC 时自动重算 mastery = AC 题数 / 关联题目总数（Task 11）
        #    spec: mastery 必须由服务端计算，客户端 new_mastery 被忽略（deprecated）。
        from app.services.progress import recompute_mastery_for_knowledge

        state.mastery = await recompute_mastery_for_knowledge(db, user_id, knowledge_id)
        # 4) mastery ≥ 0.8 → 清除 weak，并把路径项恢复为 normal
        if state.mastery >= MASTERY_THRESHOLD:
            state.is_weak = False
            await _restore_path_item_to_normal(db, user_id, knowledge_id)
        # 5) mastery ≥ 0.8 → 标记路径项为 DONE，解锁下一项
        if state.mastery >= MASTERY_THRESHOLD:
            await _mark_path_item_done(db, user_id, knowledge_id)
    else:
        state.consecutive_wa += 1
        # spec: WA 不得直接通过客户端修改 mastery。
        # mastery 只由服务端在 AC 时按 AC/总数 计算，WA 不改 mastery。
        # 仅在 consecutive_wa 达阈值时标记 weak 并触发补漏插入。
        # 不用 mastery < WEAK_MASTERY_THRESHOLD 作为触发条件：
        # 新用户 mastery 默认 0.0，一次 WA 就会触发 weak 是误判。
        # mastery 偏低仅用于"不跳过该知识点"的判断（见 generate_learning_path）。
        if state.consecutive_wa >= CONSECUTIVE_WA_THRESHOLD and not state.is_weak:
            state.is_weak = True
            # 仅在由非 weak 变 weak 时插入一次补漏
            remediation_inserted = await _insert_or_promote_remediation(db, user_id, knowledge_id)
        # 已是 weak 时，重复 WA 不再重复插入（10.2 要求）
    await db.flush()

    return AttemptResponse(
        user_id=user_id,
        knowledge_id=knowledge_id,
        consecutive_wa=state.consecutive_wa,
        is_weak=state.is_weak,
        mastery=state.mastery,
        remediation_inserted=remediation_inserted,
    )


async def _record_problem_ac(db: AsyncSession, user_id: UUID, problem_id: UUID) -> None:
    """记录用户题目 AC 状态（幂等：已存在则跳过）。"""
    from app.models.learning import UserProblemAC

    existing = (
        await db.execute(
            select(UserProblemAC).where(
                UserProblemAC.user_id == user_id,
                UserProblemAC.problem_id == problem_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(UserProblemAC(user_id=user_id, problem_id=problem_id))
        await db.flush()


async def _restore_path_item_to_normal(db: AsyncSession, user_id: UUID, knowledge_id: UUID) -> None:
    """AC 后 mastery 提升 → 把该知识点的路径项从 remediation 恢复为 normal。

    这样后续每日任务不会持续优先选择旧补漏点。
    """
    stmt = (
        select(LearningPathItem)
        .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
        .where(
            LearningPath.user_id == user_id,
            LearningPath.is_active.is_(True),
            LearningPathItem.knowledge_id == knowledge_id,
        )
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is not None and item.kind == PathItemKind.REMEDIATION:
        item.kind = PathItemKind.NORMAL
        await db.flush()


async def _mark_path_item_done(db: AsyncSession, user_id: UUID, knowledge_id: UUID) -> None:
    """mastery ≥ 0.8 时把对应路径项标记为 DONE，解锁后续 pending 项。"""
    stmt = (
        select(LearningPathItem)
        .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
        .where(
            LearningPath.user_id == user_id,
            LearningPath.is_active.is_(True),
            LearningPathItem.knowledge_id == knowledge_id,
        )
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is not None and item.status != PathItemStatus.DONE:
        item.status = PathItemStatus.DONE
        await db.flush()
        # 解锁后续 pending 项：前置已满足，可改为 active
        await _unlock_pending_items(db, user_id)


async def _unlock_pending_items(db: AsyncSession, user_id: UUID) -> None:
    """重新计算路径中 pending 项是否可解锁为 active。

    简化实现：重新加载路径所有项及其知识点，重新评估每个 pending 项的
    前置是否已全部满足（DONE 或 mastery ≥ 0.8），满足则改为 active。
    """
    from app.models.knowledge import KnowledgePrerequisite

    stmt = (
        select(LearningPathItem)
        .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPathItem.knowledge))
        .order_by(LearningPathItem.position)
    )
    items = (await db.execute(stmt)).scalars().all()
    if not items:
        return

    # 收集已 DONE 或已掌握的知识点集合
    done_kp_ids: set[UUID] = set()
    for it in items:
        if it.status == PathItemStatus.DONE:
            done_kp_ids.add(it.knowledge_id)
    # 加载 mastery ≥ 0.8 的知识点
    states = (
        (
            await db.execute(
                select(UserKnowledgeState).where(
                    UserKnowledgeState.user_id == user_id,
                    UserKnowledgeState.mastery >= MASTERY_THRESHOLD,
                )
            )
        )
        .scalars()
        .all()
    )
    for s in states:
        done_kp_ids.add(s.knowledge_id)

    # 加载所有前置依赖
    edges = (await db.execute(select(KnowledgePrerequisite))).scalars().all()
    prereq_map: dict[UUID, list[UUID]] = defaultdict(list)
    for e in edges:
        prereq_map[e.knowledge_id].append(e.prerequisite_id)

    changed = True
    while changed:
        changed = False
        for it in items:
            if it.status != PathItemStatus.PENDING:
                continue
            prereqs = prereq_map.get(it.knowledge_id, [])
            if all(p in done_kp_ids for p in prereqs):
                it.status = PathItemStatus.ACTIVE
                done_kp_ids.add(it.knowledge_id)
                changed = True
    await db.flush()


async def _insert_or_promote_remediation(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> bool:
    """在当前路径中插入或提升一个 remediation 补漏任务。

    - 若该知识点已在路径中：将 kind 改为 remediation（如还不是）
    - 若不在路径中：插入到当前 active 路径的最前端（position 重新计算）
    - 返回 True 表示实际发生了插入/提升
    """
    # 找到当前 active 路径
    path_stmt = (
        select(LearningPath)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPath.items))
    )
    path = (await db.execute(path_stmt)).scalar_one_or_none()
    if path is None:
        # 无路径：不插入，等下次 generate
        return False

    # 查找该知识点是否已在路径中
    existing: LearningPathItem | None = None
    for it in path.items:
        if it.knowledge_id == knowledge_id:
            existing = it
            break

    if existing is not None:
        if existing.kind != PathItemKind.REMEDIATION:
            existing.kind = PathItemKind.REMEDIATION
            await db.flush()
            return True
        # 已是 remediation：不重复插入
        return False

    # 不在路径中：插入到最前端
    new_item = LearningPathItem(
        path_id=path.id,
        knowledge_id=knowledge_id,
        position=0,
        kind=PathItemKind.REMEDIATION,
        status=PathItemStatus.ACTIVE,
    )
    db.add(new_item)
    await db.flush()

    # 其他项 position + 1
    other_items = [it for it in path.items if it.id != new_item.id]
    for it in other_items:
        it.position += 1
    await db.flush()
    return True


# ===== Roadmap view (路线图视图) =====


async def get_roadmap_data(
    db: AsyncSession,
    user_id: UUID,
    preview_count: int = 8,
) -> RoadmapResponse:
    """获取路线图聚合数据：知识树 + 用户学习状态。

    Returns:
        RoadmapResponse 包含所有知识点（带状态）和路径预览。
        若用户无学习路径，has_path=False，所有节点 status 均为 "none"。
    """
    # 1. 加载所有知识点
    kp_map, adj = await _load_dag(db)

    # 2. 加载 lecture_count / template_count
    kp_ids = list(kp_map.keys())
    lec_stats = (
        await db.execute(
            select(Lecture.knowledge_id, func.count(Lecture.id))
            .where(Lecture.knowledge_id.in_(kp_ids))
            .group_by(Lecture.knowledge_id)
        )
    ).all()
    tpl_stats = (
        await db.execute(
            select(CodeTemplate.knowledge_id, func.count(CodeTemplate.id))
            .where(CodeTemplate.knowledge_id.in_(kp_ids))
            .group_by(CodeTemplate.knowledge_id)
        )
    ).all()
    lec_map = {kid: cnt for kid, cnt in lec_stats}
    tpl_map = {kid: cnt for kid, cnt in tpl_stats}

    # 3. 加载用户状态
    user_states = await _load_user_states(db, user_id)

    # 4. 加载用户当前学习路径
    path_stmt = (
        select(LearningPath)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPath.items))
    )
    path = (await db.execute(path_stmt)).scalar_one_or_none()
    has_path = path is not None

    # 构建路径项索引：knowledge_id → LearningPathItem
    path_item_map: dict[UUID, LearningPathItem] = {}
    if path is not None:
        for it in path.items:
            path_item_map[it.knowledge_id] = it

    # 5. 构建前置依赖反向索引
    prereq_map: dict[UUID, list[UUID]] = defaultdict(list)
    for src, dsts in adj.items():
        for d in dsts:
            prereq_map[d].append(src)

    # 6. 已掌握知识点集合
    mastered_set: set[UUID] = set()
    for kid, st in user_states.items():
        if st.mastery >= MASTERY_THRESHOLD and not st.is_weak:
            mastered_set.add(kid)

    # 7. 为每个知识点计算状态
    tree_nodes: list[RoadmapKnowledgeNode] = []
    for kid, kp in kp_map.items():
        st = user_states.get(kid)
        path_item = path_item_map.get(kid)

        # 计算 status
        if st and st.mastery >= MASTERY_THRESHOLD and not st.is_weak:
            status = "done"
        elif path_item is not None and path_item.status == PathItemStatus.ACTIVE:
            status = "active"
        elif path_item is not None and path_item.status == PathItemStatus.PENDING:
            status = "pending"
        elif not has_path:
            status = "none"
        else:
            prereqs = prereq_map.get(kid, [])
            if all(p in mastered_set for p in prereqs):
                status = "unlocked"
            else:
                status = "none"

        tree_nodes.append(
            RoadmapKnowledgeNode(
                id=kid,
                name=kp.name,
                slug=kp.slug,
                parent_id=kp.parent_id,
                difficulty=kp.difficulty.value,
                order=kp.order,
                lecture_count=lec_map.get(kid, 0),
                template_count=tpl_map.get(kid, 0),
                status=status,
                mastery=st.mastery if st else None,
                is_weak=st.is_weak if st else False,
                path_position=path_item.position if path_item else None,
            )
        )

    # 8. 构建路径预览（拓扑排序前 N 个）
    path_preview: list[KnowledgePointRef] = []
    if has_path:
        try:
            topo = topological_sort(kp_map, adj)
        except CycleDetectedError:
            logger.warning("knowledge prerequisite graph has a cycle, skipping path preview")
        else:
            for kid in topo:
                st = user_states.get(kid)
                if st and st.mastery >= MASTERY_THRESHOLD and not st.is_weak:
                    continue
                if len(path_preview) >= preview_count:
                    break
                path_preview.append(
                    KnowledgePointRef(
                        id=kp_map[kid].id,
                        name=kp_map[kid].name,
                        slug=kp_map[kid].slug,
                    )
                )

    return RoadmapResponse(
        user_id=user_id,
        has_path=has_path,
        tree=tree_nodes,
        path_preview=path_preview,
    )
