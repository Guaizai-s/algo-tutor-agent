"""艾宾浩斯复习 service (Task 13)。

核心职责：
- 13.1 复习记录管理：学习时创建记录，复习时推进阶段
- 13.2 遗忘临界点计算：1d/2d/4d/7d/15d/30d
- 13.4 模板默写任务：基于知识点的模板代码验证
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import (
    REVIEW_INTERVALS,
    REVIEW_STAGE_ORDER,
    ReviewRecord,
    ReviewStage,
)

logger = logging.getLogger(__name__)


async def create_review_record(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> ReviewRecord:
    """创建复习记录（首次学习时调用）。

    幂等：若已存在则返回现有记录。
    """
    existing = (
        await db.execute(
            select(ReviewRecord).where(
                ReviewRecord.user_id == user_id,
                ReviewRecord.knowledge_id == knowledge_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    next_review = now + timedelta(days=REVIEW_INTERVALS[ReviewStage.INITIAL])

    record = ReviewRecord(
        user_id=user_id,
        knowledge_id=knowledge_id,
        stage=ReviewStage.INITIAL,
        last_reviewed_at=now,
        next_review_at=next_review,
        review_count=0,
    )
    db.add(record)
    await db.flush()
    return record


async def complete_review(
    db: AsyncSession,
    user_id: UUID,
    knowledge_id: UUID,
) -> ReviewRecord:
    """完成一次复习：推进到下一阶段，更新下次复习时间。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        knowledge_id: 知识点 ID

    Returns:
        更新后的 ReviewRecord

    Raises:
        ValueError: 复习记录不存在
    """
    record = (
        await db.execute(
            select(ReviewRecord).where(
                ReviewRecord.user_id == user_id,
                ReviewRecord.knowledge_id == knowledge_id,
            )
        )
    ).scalar_one_or_none()

    if record is None:
        raise ValueError(f"复习记录不存在: user={user_id}, knowledge={knowledge_id}")

    # 推进到下一阶段
    current_idx = REVIEW_STAGE_ORDER.index(record.stage) if record.stage in REVIEW_STAGE_ORDER else 0
    next_idx = min(current_idx + 1, len(REVIEW_STAGE_ORDER) - 1)
    next_stage = REVIEW_STAGE_ORDER[next_idx]

    record.stage = next_stage
    record.review_count += 1
    record.last_reviewed_at = datetime.now(UTC)

    if next_stage == ReviewStage.COMPLETED:
        record.next_review_at = None  # 复习完成，不再提醒
    else:
        interval = REVIEW_INTERVALS.get(next_stage, 30)
        record.next_review_at = datetime.now(UTC) + timedelta(days=interval)

    await db.flush()

    # 自动标记相关通知已读，避免消息中心残留未读提醒
    from app.services.push import mark_review_reminders_read

    await mark_review_reminders_read(db, user_id, knowledge_id)

    return record


async def get_due_reviews(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 5,
) -> list[ReviewRecord]:
    """获取到期待复习的记录。

    查询 next_review_at <= now 且 stage != completed 的记录。
    """
    now = datetime.now(UTC)
    records = (
        (
            await db.execute(
                select(ReviewRecord)
                .where(
                    ReviewRecord.user_id == user_id,
                    ReviewRecord.next_review_at.is_not(None),
                    ReviewRecord.next_review_at <= now,
                    ReviewRecord.stage != ReviewStage.COMPLETED,
                )
                .order_by(ReviewRecord.next_review_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(records)


async def get_all_due_reviews(
    db: AsyncSession,
    limit: int = 50,
) -> list[ReviewRecord]:
    """获取所有到期待复习的记录（Celery 定时任务用）。

    不分用户，全量查询。
    """
    now = datetime.now(UTC)
    records = (
        (
            await db.execute(
                select(ReviewRecord)
                .where(
                    ReviewRecord.next_review_at.is_not(None),
                    ReviewRecord.next_review_at <= now,
                    ReviewRecord.stage != ReviewStage.COMPLETED,
                )
                .order_by(ReviewRecord.next_review_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(records)


async def get_review_status(
    db: AsyncSession,
    user_id: UUID,
) -> dict:
    """获取用户复习状态概览。

    Returns:
        {
            "total_records": 总复习记录数,
            "completed": 已完成数,
            "due_count": 到期待复习数,
            "due_items": 到期复习项列表,
        }
    """
    now = datetime.now(UTC)

    total = (await db.execute(select(ReviewRecord).where(ReviewRecord.user_id == user_id))).scalars().all()

    completed = sum(1 for r in total if r.stage == ReviewStage.COMPLETED)
    due = [
        r
        for r in total
        if r.next_review_at is not None and r.next_review_at <= now and r.stage != ReviewStage.COMPLETED
    ]

    due_items = []
    for r in due[:5]:
        kp = (
            await db.execute(select(KnowledgePoint.name).where(KnowledgePoint.id == r.knowledge_id))
        ).scalar_one_or_none()
        due_items.append(
            {
                "knowledge_id": str(r.knowledge_id),
                "knowledge_name": kp or "unknown",
                "stage": r.stage.value,
                "next_review_at": r.next_review_at.isoformat() if r.next_review_at else None,
            }
        )

    return {
        "total_records": len(total),
        "completed": completed,
        "due_count": len(due),
        "due_items": due_items,
    }
