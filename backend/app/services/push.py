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
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import WEAK_MASTERY_THRESHOLD, UserKnowledgeState
from app.models.notification import Notification, NotificationType
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


async def get_recommendations(
    db: AsyncSession,
    user_id: UUID,
    max_per_knowledge: int = 3,
    max_knowledge_points: int = 5,
) -> RecommendationResponse:
    """基于薄弱知识点推荐未 AC 的题目。

    逻辑：
    1. 取用户薄弱知识点（mastery > 0 且 < 0.5），按 mastery 升序（越薄弱越靠前）
    2. 对每个薄弱知识点，找关联的已发布题目中用户未 AC 的
    3. 按 cf_rating 升序（简单优先），每个知识点最多取 max_per_knowledge 题
    4. 最多返回 max_knowledge_points 个知识点的推荐
    """
    # 1. 获取薄弱知识点（按 mastery 升序）
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
            .order_by(UserKnowledgeState.mastery.asc())
            .limit(max_knowledge_points)
        )
    ).all()

    if not weak_states:
        return RecommendationResponse(user_id=user_id, items=[])

    items: list[RecommendationItem] = []
    for kid, mastery, kname in weak_states:
        # 复用 recommendation.recommend_problems_by_knowledge()，避免重复查询逻辑
        candidates = await recommend_problems_by_knowledge(
            db,
            user_id,
            kid,
            limit=max_per_knowledge,
        )
        if not candidates:
            continue

        problems: list[RecommendationProblem] = [
            RecommendationProblem(
                problem_id=p.id,
                title=p.title,
                slug=p.slug,
                difficulty=p.difficulty.value,
                cf_rating=p.cf_rating,
            )
            for p in candidates
        ]

        items.append(
            RecommendationItem(
                knowledge_id=kid,
                knowledge_name=kname,
                mastery=int(mastery * 100),
                problems=problems,
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
