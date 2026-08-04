"""Task 11 + Task 8 集成：进度面板接入 CF 数据源测试。

覆盖：
- streak_days 根据 Submission 自然日记录计算
- rating_history 从 RatingHistory 返回
- 无提交/无 Rating 历史时返回 0 和空数组
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import RatingHistory, Submission
from app.services.progress import get_progress_overview


async def _create_submission(
    db_session: AsyncSession,
    user_id: UUID,
    submitted_at: datetime,
    cf_sub_id: int,
) -> None:
    """创建一条 Submission 记录。"""
    db_session.add(
        Submission(
            id=uuid4(),
            cf_submission_id=cf_sub_id,
            user_id=user_id,
            problem_id=None,
            contest_id=100,
            problem_index="A",
            handle_snapshot="testuser",
            verdict="OK",
            programming_language="Python 3",
            submitted_at=submitted_at,
            time_consumed_ms=100,
            memory_consumed_bytes=1024,
            passed_test_count=10,
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_streak_days_zero_without_submissions(db_session: AsyncSession):
    """无提交时 streak_days 为 0。"""
    user_id = uuid4()
    overview = await get_progress_overview(db_session, user_id)
    assert overview.streak_days == 0


@pytest.mark.asyncio
async def test_streak_days_today_only(db_session: AsyncSession):
    """今天有提交但昨天无，streak_days=1。"""
    user_id = uuid4()
    today = datetime.now(tz=UTC)
    await _create_submission(db_session, user_id, today, cf_sub_id=1001)

    overview = await get_progress_overview(db_session, user_id)
    assert overview.streak_days == 1


@pytest.mark.asyncio
async def test_streak_days_consecutive_days(db_session: AsyncSession):
    """连续 3 天有提交，streak_days=3。"""
    user_id = uuid4()
    now = datetime.now(tz=UTC)
    # 今天、昨天、前天各一条
    await _create_submission(db_session, user_id, now, cf_sub_id=1)
    await _create_submission(db_session, user_id, now - timedelta(days=1), cf_sub_id=2)
    await _create_submission(db_session, user_id, now - timedelta(days=2), cf_sub_id=3)

    overview = await get_progress_overview(db_session, user_id)
    assert overview.streak_days == 3


@pytest.mark.asyncio
async def test_streak_days_broken_yesterday(db_session: AsyncSession):
    """今天有提交，前天有，但昨天没有，streak=1。"""
    user_id = uuid4()
    now = datetime.now(tz=UTC)
    await _create_submission(db_session, user_id, now, cf_sub_id=1)
    await _create_submission(db_session, user_id, now - timedelta(days=2), cf_sub_id=2)

    overview = await get_progress_overview(db_session, user_id)
    assert overview.streak_days == 1  # 只有今天算


@pytest.mark.asyncio
async def test_streak_days_broken_today(db_session: AsyncSession):
    """昨天有提交，今天没有，streak=0（断签）。"""
    user_id = uuid4()
    now = datetime.now(tz=UTC)
    await _create_submission(db_session, user_id, now - timedelta(days=1), cf_sub_id=1)

    overview = await get_progress_overview(db_session, user_id)
    assert overview.streak_days == 0


@pytest.mark.asyncio
async def test_rating_history_empty_without_data(db_session: AsyncSession):
    """无 RatingHistory 时 rating_history 为空列表。"""
    user_id = uuid4()
    overview = await get_progress_overview(db_session, user_id)
    assert overview.rating_history == []


@pytest.mark.asyncio
async def test_rating_history_from_ratinghistory(db_session: AsyncSession):
    """rating_history 从 RatingHistory 表返回。"""
    user_id = uuid4()
    base_ts = datetime.now(tz=UTC)
    for i, (rating, days_ago) in enumerate([(1400, 5), (1500, 3), (1600, 1)]):
        db_session.add(
            RatingHistory(
                id=uuid4(),
                user_id=user_id,
                handle="testuser",
                contest_id=200 + i,
                contest_name=f"Contest {i}",
                rank=100,
                old_rating=rating - 100,
                new_rating=rating,
                rated_at=base_ts - timedelta(days=days_ago),
            )
        )
    await db_session.flush()

    overview = await get_progress_overview(db_session, user_id)
    assert len(overview.rating_history) == 3
    # 按时间升序
    ratings = [p.rating for p in overview.rating_history]
    assert ratings == [1400, 1500, 1600]
    # date 字段是字符串
    assert all(isinstance(p.date, str) for p in overview.rating_history)
