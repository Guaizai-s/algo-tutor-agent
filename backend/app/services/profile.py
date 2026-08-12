"""学习画像动态重估 service (P0-4)。

背景：画像目标区间只在冷启动时设置一次，之后不随做题更新，
导致目标长期冻结——用户进步/退步后推送目标不变，推荐内容脱节。

方案：基于已完成（AC）自建题的难度/CF rating 估算用户当前水平，
当估计值与当前目标区间明显偏离时动态迁移训练目标。

防抖（避免画像抖动）：
1) AC 样本数 < MIN_SIGNAL_AC 不重估（样本不足，不可信）
2) 估计值与当前区间中点偏差 < BAND_UPDATE_THRESHOLD 不重估
3) 距上次画像更新不足 DEBOUNCE_HOURS 不重估（时间窗口）
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningProfile, UserProblemAC
from app.models.problem import Problem, ProblemDifficulty, ProblemSource

logger = logging.getLogger(__name__)

# 难度 → CF Rating 锚点（自建题无 cf_rating 时按难度估算水平）
DIFFICULTY_RATING_ANCHOR: dict[ProblemDifficulty, int] = {
    ProblemDifficulty.EASY: 1000,
    ProblemDifficulty.MEDIUM: 1500,
    ProblemDifficulty.HARD: 2000,
}

MIN_SIGNAL_AC = 5  # 至少完成 5 道自建题才重估
DEBOUNCE_HOURS = 6  # 两次画像更新最小间隔（小时）
BAND_UPDATE_THRESHOLD = 100  # 估计值与当前目标中点的偏差阈值


def rating_to_target(rating: int) -> tuple[int, int]:
    """按 CF Rating 定训练目标（与冷启动共用）。

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


async def estimate_rating(db: AsyncSession, user_id: UUID) -> float | None:
    """用已完成自建题的难度/CF rating 估算用户水平。

    Returns:
        平均估计 rating；AC 样本不足时返回 None。
    """
    rows = (
        await db.execute(
            select(Problem.difficulty, Problem.cf_rating)
            .join(UserProblemAC, UserProblemAC.problem_id == Problem.id)
            .where(
                UserProblemAC.user_id == user_id,
                Problem.source == ProblemSource.PLATFORM,
            )
        )
    ).all()
    if not rows or len(rows) < MIN_SIGNAL_AC:
        return None

    ratings: list[float] = []
    for difficulty, cf_rating in rows:
        if cf_rating is not None:
            ratings.append(float(cf_rating))
        else:
            ratings.append(float(DIFFICULTY_RATING_ANCHOR.get(difficulty, 1200)))
    return sum(ratings) / len(ratings)


async def maybe_recalibrate_target(db: AsyncSession, user_id: UUID) -> bool:
    """按当前表现动态重估训练目标区间（带防抖）。

    Returns:
        是否发生了画像更新。
    """
    profile = (await db.execute(select(LearningProfile).where(LearningProfile.user_id == user_id))).scalar_one_or_none()
    if profile is None:
        return False

    # 防抖：距上次画像更新不足窗口，不做重估（避免每次做题都触发）
    last = profile.updated_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if last is not None and datetime.now(UTC) - last < timedelta(hours=DEBOUNCE_HOURS):
        return False

    est = await estimate_rating(db, user_id)
    if est is None:
        return False

    current_mid = (profile.target_rating_min + profile.target_rating_max) / 2.0
    if abs(est - current_mid) < BAND_UPDATE_THRESHOLD:
        return False

    new_min, new_max = rating_to_target(int(est))
    old_min, old_max = profile.target_rating_min, profile.target_rating_max
    if (new_min, new_max) == (old_min, old_max):
        return False

    profile.target_rating_min = new_min
    profile.target_rating_max = new_max
    await db.flush()
    logger.info(
        "user %s target recalibrated: %s-%s -> %s-%s (estimated rating=%.0f)",
        user_id,
        old_min,
        old_max,
        new_min,
        new_max,
        est,
    )
    return True
