"""推送引擎 service (Task 12 智能推送引擎)。

核心职责：
- 12.1 通知创建与管理：创建通知、查询列表、标记已读
- 12.2 复习提醒推送：艾宾浩斯遗忘曲线到期提醒
- 12.3 路径式推送：当日任务就绪通知
- 12.4 补漏式推送：薄弱知识点补漏提醒
- 12.5 推荐引擎：基于薄弱知识点推荐未 AC 题目 + 推送通知
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import (
    WEAK_MASTERY_THRESHOLD,
    LearningProfile,
    ReviewRecord,
    ReviewStage,
    UserKnowledgeState,
    UserProblemAC,
)
from app.models.notification import Notification, NotificationType
from app.models.problem import Problem
from app.models.wrongbook import WrongBookEntry
from app.schemas.notification import RecommendationItem, RecommendationProblem, RecommendationResponse
from app.services.recommendation import recommend_problems_by_knowledge

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    notification_type: NotificationType,
    title: str,
    body: str,
    *,
    related_knowledge_id: UUID | None = None,
    related_problem_id: UUID | None = None,
) -> Notification:
    """创建一条通知。

    Args:
        db: 数据库会话
        user_id: 接收通知的用户 ID
        notification_type: 通知类型
        title: 通知标题
        body: 通知正文
        related_knowledge_id: 关联知识点 ID
        related_problem_id: 关联题目 ID

    Returns:
        创建的 Notification 对象
    """
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        related_knowledge_id=related_knowledge_id,
        related_problem_id=related_problem_id,
    )
    db.add(notification)
    await db.flush()
    logger.info("notification created: type=%s, user=%s, id=%s", notification_type.value, user_id, notification.id)
    return notification


async def get_notifications(
    db: AsyncSession,
    user_id: UUID,
    *,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Notification], int, int]:
    """获取用户通知列表。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        unread_only: 仅返回未读通知
        limit: 每页数量
        offset: 偏移量

    Returns:
        (通知列表, 总数, 未读数)
    """
    base_query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        base_query = base_query.where(Notification.is_read == False)  # noqa: E712

    # 总数
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar_one()

    # 未读数
    unread_count = (
        await db.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
        )
    ).scalar_one()

    # 分页列表
    items = (
        (await db.execute(base_query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )

    return list(items), total, unread_count


async def mark_read(
    db: AsyncSession,
    notification_id: UUID,
    user_id: UUID,
) -> Notification | None:
    """标记单条通知为已读。

    Args:
        db: 数据库会话
        notification_id: 通知 ID
        user_id: 用户 ID（用于权限校验）

    Returns:
        更新后的 Notification，若不存在或不属于该用户则返回 None
    """
    result = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if result is None:
        return None

    if not result.is_read:
        result.is_read = True
        result.read_at = datetime.now(UTC)
        await db.flush()

    return result


async def mark_all_read(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """标记用户所有未读通知为已读。

    Returns:
        被标记为已读的通知数量
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=now)
    )
    await db.flush()
    return result.rowcount


async def send_review_reminder(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
    knowledge_name: str,
    stage: str,
) -> Notification:
    """发送复习提醒通知（Task 13.3 调用）。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        knowledge_id: 知识点 ID
        knowledge_name: 知识点名称
        stage: 当前复习阶段

    Returns:
        创建的 Notification
    """
    title = f"复习提醒：{knowledge_name}"
    body = f"你学习「{knowledge_name}」已到复习阶段（{stage}），建议做一道变体题巩固记忆。"
    return await create_notification(
        db,
        user_id=user_id,
        notification_type=NotificationType.REVIEW_REMINDER,
        title=title,
        body=body,
        related_knowledge_id=knowledge_id,
    )


async def send_daily_task_reminder(
    db: AsyncSession,
    user_id: UUID,
    knowledge_name: str,
    is_remediation: bool = False,
) -> Notification:
    """发送当日任务提醒通知（路径式推送）。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        knowledge_name: 目标知识点名称
        is_remediation: 是否为补漏任务

    Returns:
        创建的 Notification
    """
    if is_remediation:
        title = f"补漏提醒：{knowledge_name}"
        body = f"你在「{knowledge_name}」连续出错，已生成补漏任务，请查看当日任务。"
        ntype = NotificationType.REMEDIATION
    else:
        title = f"今日学习：{knowledge_name}"
        body = f"今日任务已生成，主题：「{knowledge_name}」，包含讲义 + 4 道练习题。"
        ntype = NotificationType.DAILY_TASK

    return await create_notification(
        db,
        user_id=user_id,
        notification_type=ntype,
        title=title,
        body=body,
    )


# ===== 推荐引擎 (Task 12.5) =====

# 复习到期时间窗（小时）：next_review_at 落在此窗口内视为"即将/已到期"，参与加权
REVIEW_DUE_WINDOW_HOURS = 24

# 默认训练目标区间（无 LearningProfile 时，银牌向 1200-1600）
DEFAULT_TARGET_MIN = 1200
DEFAULT_TARGET_MAX = 1600


def _band_distance(rating: float | None, target_min: float, target_max: float) -> float:
    """计算题目 cf_rating 与目标区间的距离（0 = 落在区间内，None = 无穷远）。"""
    if rating is None:
        return float("inf")
    if rating < target_min:
        return target_min - rating
    if rating > target_max:
        return rating - target_max
    return 0.0


async def get_recommendations(
    db: AsyncSession,
    user_id: UUID,
    max_per_knowledge: int = 3,
    max_knowledge_points: int = 5,
) -> RecommendationResponse:
    """多信号融合推荐未 AC 的题目（P1-1 推荐融合）。

    信号与优先级：
    1. 薄弱知识点（mastery > 0 且 < 0.5）为入口，mastery 越低越靠前
    2. 知识点间次级排序：艾宾浩斯复习到期（review_due）优先
    3. 知识点内题目排序：
       a. 错题本中未解决的题目（错题重做）最高优先级
       b. 与用户已 AC 题目标签重合的题（题型偏好）次之
       c. 距目标 rating 区间最近的题（难度匹配）再次之
       d. 同条件下 cf_rating 升序（简单优先）
    4. 每个知识点/题目附带推荐理由（reasons 字段），供前端展示
    """
    now = datetime.now(UTC)

    # 1. 薄弱知识点（先取全部，融合排序后再截断）
    weak_states = (
        await db.execute(
            select(
                UserKnowledgeState.knowledge_id,
                UserKnowledgeState.mastery,
                KnowledgePoint.name,
            )
            .join(KnowledgePoint, KnowledgePoint.id == UserKnowledgeState.knowledge_id)
            .where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.mastery > 0.0,
                UserKnowledgeState.mastery < WEAK_MASTERY_THRESHOLD,
            )
        )
    ).all()

    if not weak_states:
        return RecommendationResponse(user_id=user_id, items=[])

    # 2. 复习到期信号：已到期/即将到期（24h 窗口内）且未完成的复习记录
    review_rows = (
        await db.execute(
            select(ReviewRecord.knowledge_id, ReviewRecord.next_review_at).where(
                ReviewRecord.user_id == user_id,
                ReviewRecord.next_review_at.is_not(None),
                ReviewRecord.next_review_at <= now + timedelta(hours=REVIEW_DUE_WINDOW_HOURS),
                ReviewRecord.stage != ReviewStage.COMPLETED,
            )
        )
    ).all()
    review_due: dict[UUID, datetime] = {kid: t for kid, t in review_rows}

    # 3. 错题信号：未解决错题的 problem_id 集合（错题重做优先）
    wrong_rows = (
        await db.execute(
            select(WrongBookEntry.problem_id, func.count(WrongBookEntry.id))
            .where(
                WrongBookEntry.user_id == user_id,
                WrongBookEntry.resolved == False,  # noqa: E712
                WrongBookEntry.problem_id.is_not(None),
            )
            .group_by(WrongBookEntry.problem_id)
        )
    ).all()
    wrongbook_ids = {pid for pid, _count in wrong_rows}

    # 4. 题型偏好：用户已 AC 题目的标签集合
    ac_tag_rows = (
        (
            await db.execute(
                select(Problem.cf_tags)
                .join(UserProblemAC, UserProblemAC.problem_id == Problem.id)
                .where(UserProblemAC.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    ac_tags: set[str] = {tag for tags in ac_tag_rows if tags for tag in tags}

    # 5. 目标 rating 区间（无画像时用默认值，GET 场景不落库）
    profile = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalar_one_or_none()
    tmin = float(profile.target_rating_min) if profile else float(DEFAULT_TARGET_MIN)
    tmax = float(profile.target_rating_max) if profile else float(DEFAULT_TARGET_MAX)

    # 知识点融合排序：mastery 升序（越薄弱越靠前）→ 复习到期优先 → 下次复习时间升序
    weak_states.sort(
        key=lambda row: (
            row.mastery,
            0 if row.knowledge_id in review_due else 1,
            review_due.get(row.knowledge_id, datetime.max.replace(tzinfo=UTC)),
        )
    )

    def _tag_match(p: Problem) -> bool:
        return bool(p.cf_tags) and bool(set(p.cf_tags) & ac_tags)

    items: list[RecommendationItem] = []
    for kid, mastery, kname in weak_states[:max_knowledge_points]:
        # 扩大候选池再精排（避免每知识点只取 max 个导致融合排序没有意义）
        candidates = await recommend_problems_by_knowledge(
            db,
            user_id,
            kid,
            limit=max_per_knowledge * 4,
        )
        if not candidates:
            continue

        candidates.sort(
            key=lambda p: (
                0 if p.id in wrongbook_ids else 1,
                0 if _tag_match(p) else 1,
                _band_distance(p.cf_rating, tmin, tmax),
                p.cf_rating if p.cf_rating is not None else float("inf"),
                p.created_at,
            )
        )

        problems: list[RecommendationProblem] = []
        for p in candidates[:max_per_knowledge]:
            reasons: list[str] = []
            if p.id in wrongbook_ids:
                reasons.append("错题重做")
            if _tag_match(p):
                reasons.append("题型偏好匹配")
            if p.cf_rating is not None and tmin <= p.cf_rating <= tmax:
                reasons.append("难度贴合目标区间")
            if not reasons:
                reasons.append("薄弱知识点补漏")
            problems.append(
                RecommendationProblem(
                    problem_id=p.id,
                    title=p.title,
                    slug=p.slug,
                    difficulty=p.difficulty.value,
                    cf_rating=p.cf_rating,
                    tags=p.cf_tags or [],
                    reasons=reasons,
                )
            )

        item_reasons = [f"薄弱知识点（掌握度 {int(mastery * 100)}%）"]
        if kid in review_due:
            item_reasons.append("复习到期")
        items.append(
            RecommendationItem(
                knowledge_id=kid,
                knowledge_name=kname,
                mastery=int(mastery * 100),
                problems=problems,
                review_due=kid in review_due,
                next_review_at=review_due.get(kid),
                reasons=item_reasons,
            )
        )

    return RecommendationResponse(user_id=user_id, items=items)


async def send_recommendation_push(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """为单个用户生成推荐题目并推送通知。

    对每个薄弱知识点推送一条 remediation 通知，包含推荐题目信息。
    如果用户已有未读的 remediation 通知（同一天内），则跳过避免重复推送。

    Returns:
        创建的推送通知数量
    """
    recs = await get_recommendations(db, user_id, max_per_knowledge=2, max_knowledge_points=3)
    if not recs.items:
        return 0

    # 检查今天是否已发送过补漏通知（防重复）
    today = datetime.now(UTC).date()
    existing = (
        await db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.notification_type == NotificationType.REMEDIATION,
                func.date(Notification.created_at) == today,
            )
        )
    ).scalar_one()

    if existing > 0:
        logger.info(
            "send_recommendation_push: user %s already has %d remediation notifications today, skip", user_id, existing
        )
        return 0

    sent = 0
    for item in recs.items:
        problem_titles = [p.title for p in item.problems[:2]]
        body = (
            f"「{item.knowledge_name}」掌握度仅 {item.mastery}%，建议练习："
            + "、".join(problem_titles)
            + "。打开今日学习查看全部推荐。"
        )
        if item.review_due:
            body = f"「{item.knowledge_name}」已到复习期，先回顾再练题：{body}"
        await create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.REMEDIATION,
            title=f"补漏推荐：{item.knowledge_name}",
            body=body,
            related_knowledge_id=item.knowledge_id,
        )
        sent += 1

    logger.info("send_recommendation_push: user %s, sent %d notifications", user_id, sent)
    return sent


async def get_all_users_with_weak_points(
    db: AsyncSession,
    limit: int = 100,
) -> list[UUID]:
    """获取所有有薄弱知识点的用户 ID 列表（用于 Celery 批量推送）。

    Args:
        db: 数据库会话
        limit: 最大返回用户数

    Returns:
        用户 ID 列表
    """
    rows = (
        (
            await db.execute(
                select(func.distinct(UserKnowledgeState.user_id))
                .where(
                    UserKnowledgeState.mastery > 0.0,
                    UserKnowledgeState.mastery < WEAK_MASTERY_THRESHOLD,
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def send_batch_recommendation_push(
    db: AsyncSession,
    limit: int = 100,
) -> dict:
    """批量推送：为所有有薄弱知识点的用户推送推荐通知。

    Args:
        db: 数据库会话
        limit: 最多处理用户数

    Returns:
        {"total_users": N, "notified_users": N, "notifications_sent": N}
    """
    user_ids = await get_all_users_with_weak_points(db, limit)
    notified = 0
    total_sent = 0
    for uid in user_ids:
        sent = await send_recommendation_push(db, uid)
        if sent > 0:
            notified += 1
            total_sent += sent
    logger.info(
        "send_batch_recommendation_push: total_users=%d, notified=%d, notifications=%d",
        len(user_ids),
        notified,
        total_sent,
    )
    return {
        "total_users": len(user_ids),
        "notified_users": notified,
        "notifications_sent": total_sent,
    }


async def mark_review_reminders_read(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> int:
    """用户完成某知识点的复习后，自动标记相关 review_reminder 通知为已读。

    避免用户已在 Review 页面完成复习但消息中心仍有未读提醒。

    Returns:
        被标记为已读的通知数量
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.related_knowledge_id == knowledge_id,
            Notification.notification_type == NotificationType.REVIEW_REMINDER,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=now)
    )
    await db.flush()
    logger.info(
        "mark_review_reminders_read: user=%s, knowledge=%s, marked=%d",
        user_id,
        knowledge_id,
        result.rowcount,
    )
    return result.rowcount
