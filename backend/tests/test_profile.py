"""P0-4 画像自适应测试。

覆盖：
1. estimate_rating：样本不足返回 None；难度/CF rating 估算正确
2. rating_to_target：训练目标区间边界映射
3. maybe_recalibrate_target：无画像/样本不足/防抖/偏差不足不更新；
   强信号且防抖窗口已过时正确迁移目标区间
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningProfile, UserProblemAC
from app.models.problem import Problem, ProblemDifficulty, ProblemSource, ProblemStatus
from app.services.profile import (
    DEBOUNCE_HOURS,
    MIN_SIGNAL_AC,
    estimate_rating,
    maybe_recalibrate_target,
    rating_to_target,
)


@pytest.fixture
async def platform_problems(db_session: AsyncSession) -> list[Problem]:
    """6 道 EASY 自建题（source=platform），供用户 AC。"""
    suffix = uuid4().hex[:8]
    problems = [
        Problem(
            id=uuid4(),
            title=f"画像题 {i}",
            slug=f"profile-p{i}-{suffix}",
            description="test",
            difficulty=ProblemDifficulty.EASY,
            status=ProblemStatus.PUBLISHED,
            source=ProblemSource.PLATFORM,
            cf_rating=None,
        )
        for i in range(6)
    ]
    db_session.add_all(problems)
    await db_session.flush()
    return problems


async def _ac_problems(db_session: AsyncSession, user_id: UUID, problems: list[Problem]) -> None:
    """用户 AC 指定题目，并创建默认画像（1200-1600，updated_at=now）。"""
    for p in problems:
        db_session.add(UserProblemAC(user_id=user_id, problem_id=p.id))
    db_session.add(LearningProfile(user_id=user_id, target_rating_min=1200, target_rating_max=1600))
    await db_session.flush()


async def _backdate_profile(db_session: AsyncSession, user_id: UUID) -> None:
    """把画像 updated_at 回拨到防抖窗口之外（Core UPDATE 不触发 ORM onupdate）。"""
    past = datetime.now(UTC) - timedelta(hours=DEBOUNCE_HOURS + 1)
    await db_session.execute(
        sa_update(LearningProfile).where(LearningProfile.user_id == user_id).values(updated_at=past)
    )
    # Core UPDATE 不会同步 ORM 身份映射中的对象，过期后下次查询才会从 DB 刷新
    db_session.expire_all()


# ===== 1. rating_to_target 边界映射 =====


async def test_rating_to_target_boundaries() -> None:
    assert rating_to_target(800) == (800, 1200)
    assert rating_to_target(1199) == (800, 1200)
    assert rating_to_target(1200) == (1200, 1600)
    assert rating_to_target(1599) == (1200, 1600)
    assert rating_to_target(1600) == (1600, 2000)
    assert rating_to_target(2500) == (2000, 2600)


# ===== 2. estimate_rating =====


async def test_estimate_rating_insufficient_samples(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """AC 数 < MIN_SIGNAL_AC 时样本不足，返回 None。"""
    user_id = uuid4()
    await _ac_problems(db_session, user_id, platform_problems[: MIN_SIGNAL_AC - 1])
    assert await estimate_rating(db_session, user_id) is None


async def test_estimate_rating_by_difficulty(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """AC 5 道 EASY 自建题（无 cf_rating）→ 估计 1000。"""
    user_id = uuid4()
    await _ac_problems(db_session, user_id, platform_problems[:MIN_SIGNAL_AC])
    assert await estimate_rating(db_session, user_id) == pytest.approx(1000.0)


async def test_estimate_rating_uses_cf_rating(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """题目带 cf_rating 时优先使用 cf_rating，而不是难度锚点。"""
    suffix = uuid4().hex[:8]
    rated = [
        Problem(
            id=uuid4(),
            title=f"画像带分题 {i}",
            slug=f"profile-rated-{i}-{suffix}",
            description="test",
            difficulty=ProblemDifficulty.EASY,
            status=ProblemStatus.PUBLISHED,
            source=ProblemSource.PLATFORM,
            cf_rating=1700.0,
        )
        for i in range(MIN_SIGNAL_AC)
    ]
    db_session.add_all(rated)
    await db_session.flush()

    user_id = uuid4()
    await _ac_problems(db_session, user_id, rated)
    assert await estimate_rating(db_session, user_id) == pytest.approx(1700.0)


# ===== 3. maybe_recalibrate_target =====


async def test_recalibrate_no_profile(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """无画像时不重估。"""
    user_id = uuid4()
    assert await maybe_recalibrate_target(db_session, user_id) is False


async def test_recalibrate_insufficient_signal(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """样本不足时不重估。"""
    user_id = uuid4()
    await _ac_problems(db_session, user_id, platform_problems[: MIN_SIGNAL_AC - 1])
    await _backdate_profile(db_session, user_id)
    assert await maybe_recalibrate_target(db_session, user_id) is False


async def test_recalibrate_debounced(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """防抖窗口内不重估（画像刚初始化，updated_at=now）。"""
    user_id = uuid4()
    await _ac_problems(db_session, user_id, platform_problems[:MIN_SIGNAL_AC])
    assert await maybe_recalibrate_target(db_session, user_id) is False


async def test_recalibrate_updates_target(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """强信号且防抖窗口已过：5 道 EASY AC（est=1000）→ 目标迁移到 800-1200。"""
    user_id = uuid4()
    await _ac_problems(db_session, user_id, platform_problems[:MIN_SIGNAL_AC])
    await _backdate_profile(db_session, user_id)

    updated = await maybe_recalibrate_target(db_session, user_id)
    assert updated is True

    profile = (
        await db_session.execute(sa_select(LearningProfile).where(LearningProfile.user_id == user_id))
    ).scalar_one()
    assert (profile.target_rating_min, profile.target_rating_max) == (800, 1200)


async def test_recalibrate_within_threshold(db_session: AsyncSession, platform_problems: list[Problem]) -> None:
    """估计值与当前目标中点偏差不足阈值时不更新。"""
    user_id = uuid4()
    # 画像初始 800-1200（中点 1000），AC 5 道 EASY → est=1000，偏差 0
    db_session.add(LearningProfile(user_id=user_id, target_rating_min=800, target_rating_max=1200))
    for p in platform_problems[:MIN_SIGNAL_AC]:
        db_session.add(UserProblemAC(user_id=user_id, problem_id=p.id))
    await db_session.flush()
    await _backdate_profile(db_session, user_id)

    assert await maybe_recalibrate_target(db_session, user_id) is False
