"""当日任务生成 service (Task 10.3)。

规则：
- 1 个 LectureLevel.CARD 讲义
- 1 道模板题：cf_rating <= 训练目标下限
- 2 道应用题：训练目标下限 <= cf_rating <= 训练目标上限
- 1 道挑战题：cf_rating >= 训练目标上限，挑战题允许缺省
- 所有题目必须与目标知识点通过 ProblemKnowledgePoint 关联
- 只推荐已发布题目
- 同一份每日任务内题目不得重复
- 同一用户、同一自然日重复请求必须返回同一份计划（幂等）
- 候选不足时返回已有任务 + missing_slots，不抛 500，不跨知识点补题
- 日期按 Asia/Shanghai 自然日
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge import KnowledgePoint, Lecture, LectureLevel
from app.models.learning import (
    DailyTask,
    DailyTaskItem,
    DailyTaskItemStatus,
    DailyTaskItemType,
    LearningPath,
    LearningPathItem,
    PathItemKind,
    PathItemStatus,
)
from app.models.problem import Problem
from app.schemas.learning import (
    DailyTaskItemRead,
    DailyTaskPathPreviewItem,
    DailyTaskRead,
    DailyTaskTodayResponse,
    KnowledgePointRef,
    LectureRef,
    ProblemRef,
)
from app.services.recommendation import recommend_for_slots

logger = logging.getLogger(__name__)

# Asia/Shanghai 时区（UTC+8），不依赖 tzdata 包
SHANGHAI_TZ = timezone(timedelta(hours=8))


def today_shanghai() -> date:
    """当前 Asia/Shanghai 自然日。"""
    return datetime.now(SHANGHAI_TZ).date()


async def get_or_create_today_task(
    db: AsyncSession,
    user_id: UUID,
) -> DailyTaskTodayResponse:
    """获取或创建今日任务（幂等）。

    - 同一用户、同一自然日重复请求返回同一份计划
    - 若今日已存在记录，直接返回
    - 否则选取当前路径的第一个 active/remediation 节点作为目标知识点
    """
    today = today_shanghai()

    # 幂等检查
    existing = await _load_today_task(db, user_id, today)
    if existing is not None:
        task_read = await _build_task_read(db, existing)
        preview = await _build_path_preview(db, user_id)
        return DailyTaskTodayResponse(task=task_read, path_preview=preview)

    # 选目标知识点
    target_kp, is_remediation = await _select_target_knowledge(db, user_id)
    if target_kp is None:
        # 无路径：创建一个空任务占位，避免反复生成
        # 但仍需要一个 knowledge_id（NOT NULL），这里抛 404 由 router 处理
        raise ValueError("用户尚未生成学习路径，无法生成当日任务")

    # 推荐候选
    template, application, challenge, _no_rating, _profile = await recommend_for_slots(db, user_id, target_kp.id)

    # CARD 讲义
    lecture_card = await _pick_card_lecture(db, target_kp.id)

    # 同一任务内题目不得重复
    used_problem_ids: set[UUID] = set()

    task = DailyTask(
        user_id=user_id,
        task_date=today,
        knowledge_id=target_kp.id,
        is_remediation=is_remediation,
        missing_slots="",
    )
    db.add(task)
    try:
        await db.flush()
    except IntegrityError:
        # 并发场景：另一个请求已先创建了今日任务（uq_user_daily_task 拦截）。
        # 回滚后重新读取已存在的任务返回（幂等语义）。
        await db.rollback()
        existing = await _load_today_task(db, user_id, today)
        if existing is not None:
            task_read = await _build_task_read(db, existing)
            preview = await _build_path_preview(db, user_id)
            return DailyTaskTodayResponse(task=task_read, path_preview=preview)
        raise

    position = 0
    missing_slots: list[str] = []

    # 1. CARD 讲义
    if lecture_card is not None:
        db.add(
            DailyTaskItem(
                task_id=task.id,
                item_type=DailyTaskItemType.LECTURE_CARD,
                position=position,
                lecture_id=lecture_card.id,
                status=DailyTaskItemStatus.PENDING,
            )
        )
        position += 1
    else:
        missing_slots.append(DailyTaskItemType.LECTURE_CARD.value)
        db.add(
            DailyTaskItem(
                task_id=task.id,
                item_type=DailyTaskItemType.LECTURE_CARD,
                position=position,
                lecture_id=None,
                status=DailyTaskItemStatus.PENDING,
                missing_reason="no CARD lecture for this knowledge point",
            )
        )
        position += 1

    # 2. 模板题（1 道）
    position = await _add_problem_slot(
        db,
        task.id,
        DailyTaskItemType.TEMPLATE_PROBLEM,
        position,
        template,
        used_problem_ids,
        missing_slots,
    )

    # 3. 应用题（2 道）
    for _ in range(2):
        position = await _add_problem_slot(
            db,
            task.id,
            DailyTaskItemType.APPLICATION_PROBLEM,
            position,
            application,
            used_problem_ids,
            missing_slots,
        )

    # 4. 挑战题（1 道，允许缺省）
    position = await _add_problem_slot(
        db,
        task.id,
        DailyTaskItemType.CHALLENGE_PROBLEM,
        position,
        challenge,
        used_problem_ids,
        missing_slots,
        allow_missing=True,
    )

    task.missing_slots = ",".join(missing_slots)
    await db.flush()

    task_read = await _build_task_read(db, task)
    preview = await _build_path_preview(db, user_id)
    return DailyTaskTodayResponse(task=task_read, path_preview=preview)


async def _add_problem_slot(
    db: AsyncSession,
    task_id: UUID,
    item_type: DailyTaskItemType,
    position: int,
    candidates: list,
    used_problem_ids: set[UUID],
    missing_slots: list[str],
    allow_missing: bool = False,
) -> int:
    """从候选中取一道未用过的题写入任务项。返回下一个 position。"""
    chosen = None
    for p in candidates:
        if p.id not in used_problem_ids:
            chosen = p
            break
    if chosen is not None:
        used_problem_ids.add(chosen.id)
        db.add(
            DailyTaskItem(
                task_id=task_id,
                item_type=item_type,
                position=position,
                problem_id=chosen.id,
                status=DailyTaskItemStatus.PENDING,
            )
        )
        return position + 1

    # 候选不足
    missing_slots.append(item_type.value)
    db.add(
        DailyTaskItem(
            task_id=task_id,
            item_type=item_type,
            position=position,
            problem_id=None,
            status=DailyTaskItemStatus.PENDING,
            missing_reason=f"no published problem in rating range for {item_type.value}",
        )
    )
    return position + 1


async def _pick_card_lecture(db: AsyncSession, knowledge_id: UUID) -> Lecture | None:
    """选择某知识点的 CARD 讲义。"""
    stmt = select(Lecture).where(
        Lecture.knowledge_id == knowledge_id,
        Lecture.level == LectureLevel.CARD,
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return None
    # 若有多张 CARD，取 created_at 最旧的（稳定）
    return min(rows, key=lambda lec: (lec.created_at, lec.title))


async def _select_target_knowledge(db: AsyncSession, user_id: UUID) -> tuple[KnowledgePoint | None, bool]:
    """从当前路径中选取目标知识点。

    优先级：
    1. 第一个 kind=remediation 的项（补漏优先）
    2. 否则第一个 status=active 的 normal 项
    3. 否则第一个 status=pending 的项（前置未满足但仍可生成任务）
    """
    stmt = (
        select(LearningPathItem)
        .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPathItem.knowledge))
        .order_by(LearningPathItem.position)
    )
    items = (await db.execute(stmt)).scalars().all()
    if not items:
        return None, False

    # 1. remediation 优先
    for it in items:
        if it.kind == PathItemKind.REMEDIATION:
            return it.knowledge, True
    # 2. active normal
    for it in items:
        if it.status == PathItemStatus.ACTIVE:
            return it.knowledge, False
    # 3. 兜底：第一个
    return items[0].knowledge, items[0].kind == PathItemKind.REMEDIATION


async def _load_today_task(db: AsyncSession, user_id: UUID, today: date) -> DailyTask | None:
    stmt = (
        select(DailyTask)
        .where(DailyTask.user_id == user_id, DailyTask.task_date == today)
        .options(selectinload(DailyTask.knowledge))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _build_task_read(db: AsyncSession, task: DailyTask) -> DailyTaskRead:
    """构造 DailyTaskRead 响应。"""
    # 重新查询 items + 关联
    stmt = select(DailyTaskItem).where(DailyTaskItem.task_id == task.id).order_by(DailyTaskItem.position)
    items = (await db.execute(stmt)).scalars().all()

    # 批量加载 lecture + problem
    lecture_ids = [it.lecture_id for it in items if it.lecture_id is not None]
    problem_ids = [it.problem_id for it in items if it.problem_id is not None]

    lectures_map: dict[UUID, Lecture] = {}
    if lecture_ids:
        lec_rows = (await db.execute(select(Lecture).where(Lecture.id.in_(lecture_ids)))).scalars().all()
        lectures_map = {lec.id: lec for lec in lec_rows}

    problems_map: dict[UUID, Problem] = {}
    if problem_ids:
        prob_rows = (await db.execute(select(Problem).where(Problem.id.in_(problem_ids)))).scalars().all()
        problems_map = {p.id: p for p in prob_rows}

    # knowledge
    kp = task.knowledge
    if kp is None:
        kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == task.knowledge_id))).scalar_one()

    missing = [s for s in (task.missing_slots or "").split(",") if s]

    return DailyTaskRead(
        id=task.id,
        user_id=task.user_id,
        task_date=task.task_date,
        knowledge=KnowledgePointRef(id=kp.id, name=kp.name, slug=kp.slug),
        is_remediation=task.is_remediation,
        missing_slots=missing,
        items=[
            DailyTaskItemRead(
                id=it.id,
                item_type=it.item_type,
                position=it.position,
                lecture=(
                    LectureRef(
                        id=lectures_map[it.lecture_id].id,
                        knowledge_id=lectures_map[it.lecture_id].knowledge_id,
                        level=lectures_map[it.lecture_id].level.value,
                        title=lectures_map[it.lecture_id].title,
                    )
                    if it.lecture_id and it.lecture_id in lectures_map
                    else None
                ),
                problem=(
                    ProblemRef(
                        id=problems_map[it.problem_id].id,
                        title=problems_map[it.problem_id].title,
                        slug=problems_map[it.problem_id].slug,
                        difficulty=problems_map[it.problem_id].difficulty.value,
                        cf_rating=problems_map[it.problem_id].cf_rating,
                    )
                    if it.problem_id and it.problem_id in problems_map
                    else None
                ),
                status=it.status,
                missing_reason=it.missing_reason,
            )
            for it in items
        ],
    )


async def _build_path_preview(db: AsyncSession, user_id: UUID) -> list[DailyTaskPathPreviewItem]:
    """构造路径预览（前 N 项）。"""
    stmt = (
        select(LearningPathItem)
        .join(LearningPath, LearningPath.id == LearningPathItem.path_id)
        .where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        .options(selectinload(LearningPathItem.knowledge))
        .order_by(LearningPathItem.position)
        .limit(10)
    )
    items = (await db.execute(stmt)).scalars().all()
    return [
        DailyTaskPathPreviewItem(
            knowledge_id=it.knowledge_id,
            name=it.knowledge.name if it.knowledge else "",
            position=it.position,
            kind=it.kind,
        )
        for it in items
    ]
