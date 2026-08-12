"""P1-2 掌握度升级：多信号 mastery 计算测试。

覆盖：
1. apply_mastery_signals 纯函数：连续 WA 惩罚（阈值/封顶/不为负）
2. apply_mastery_signals 纯函数：时间衰减（grace 期/衰减/封底）
3. record_attempt 集成：3 次连续 WA 后 AC，mastery 受惩罚且清零连续 WA
4. 时间衰减集成：recompute 对长期未活动的知识点回落 mastery
5. 无信号时不改变基线（回归保护）
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import UserKnowledgeState
from app.models.problem import Problem, ProblemDifficulty, ProblemKnowledgePoint, ProblemStatus
from app.services.learning_path import record_attempt
from app.services.progress import (
    INACTIVE_GRACE_DAYS,
    TIME_DECAY_FLOOR,
    WA_PENALTY_CAP,
    WA_PENALTY_STEP,
    apply_mastery_signals,
    recompute_mastery_for_knowledge,
)


@pytest.fixture
async def kp_single(db_session: AsyncSession) -> dict[str, UUID]:
    """单个知识点，关联 1 道已发布题（AC 后基线 mastery=1.0）。"""
    suffix = uuid4().hex[:8]
    kp = KnowledgePoint(
        id=uuid4(),
        name=f"P1-2-{suffix}",
        slug=f"p12-{suffix}",
        description="test",
        order=-6000,
    )
    p = Problem(
        id=uuid4(),
        title="P1-2 题",
        slug=f"p12-p-{suffix}",
        description="test",
        difficulty=ProblemDifficulty.EASY,
        status=ProblemStatus.PUBLISHED,
        cf_rating=1000.0,
    )
    db_session.add_all([kp, p])
    await db_session.flush()
    db_session.add(ProblemKnowledgePoint(problem_id=p.id, knowledge_id=kp.id))
    await db_session.flush()
    return {"kp": kp.id, "p": p.id}


async def _backdate_state(db_session: AsyncSession, user_id: UUID, kp_id: UUID, days: int) -> None:
    """把 state 的 updated_at 回拨（Core UPDATE 不触发 ORM onupdate）。"""
    past = datetime.now(UTC) - timedelta(days=days)
    await db_session.execute(
        sa_update(UserKnowledgeState)
        .where(
            UserKnowledgeState.user_id == user_id,
            UserKnowledgeState.knowledge_id == kp_id,
        )
        .values(updated_at=past)
    )
    db_session.expire_all()


# ===== 1. 连续 WA 惩罚（纯函数） =====


def test_wa_penalty_below_threshold() -> None:
    """连续 WA < 3 次不惩罚。"""
    assert apply_mastery_signals(0.8, 0) == pytest.approx(0.8)
    assert apply_mastery_signals(0.8, 2) == pytest.approx(0.8)


def test_wa_penalty_at_threshold_and_cap() -> None:
    """3 次起扣一步，多次封顶。"""
    assert apply_mastery_signals(0.8, 3) == pytest.approx(0.8 - WA_PENALTY_STEP)
    assert apply_mastery_signals(0.8, 100) == pytest.approx(0.8 - WA_PENALTY_CAP)


def test_wa_penalty_never_negative() -> None:
    """惩罚不使 mastery 为负。"""
    assert apply_mastery_signals(0.01, 100) == pytest.approx(0.0)


# ===== 2. 时间衰减（纯函数） =====


def test_time_decay_grace_period() -> None:
    """grace 期（含边界）内不衰减。"""
    now = datetime.now(UTC)
    v = apply_mastery_signals(0.8, 0, now - timedelta(days=INACTIVE_GRACE_DAYS), now=now)
    assert v == pytest.approx(0.8)


def test_time_decay_after_grace() -> None:
    """超过 grace 期开始衰减。"""
    now = datetime.now(UTC)
    v = apply_mastery_signals(0.8, 0, now - timedelta(days=20), now=now)
    assert 0.0 < v < 0.8


def test_time_decay_floor() -> None:
    """衰减封底 TIME_DECAY_FLOOR。"""
    now = datetime.now(UTC)
    v = apply_mastery_signals(0.8, 0, now - timedelta(days=90), now=now)
    assert v == pytest.approx(0.8 * TIME_DECAY_FLOOR)


# ===== 3. record_attempt 集成：连续 WA 后 AC =====


async def test_ac_after_three_wa_penalized(db_session: AsyncSession, kp_single: dict[str, UUID]) -> None:
    """3 次连续 WA 后 AC：mastery = 基线 - 一步惩罚，连续 WA 清零。"""
    user_id = uuid4()
    for _ in range(3):
        await record_attempt(db_session, user_id, kp_single["kp"], kp_single["p"], "WA")

    resp = await record_attempt(db_session, user_id, kp_single["kp"], kp_single["p"], "AC")
    # 基线 1.0，3 次连续 WA 扣 WA_PENALTY_STEP
    assert resp.mastery == pytest.approx(1.0 - WA_PENALTY_STEP)
    assert resp.consecutive_wa == 0
    # 0.97 ≥ 0.8 → 清除 weak
    assert resp.is_weak is False


async def test_ac_clean_first_try_no_penalty(db_session: AsyncSession, kp_single: dict[str, UUID]) -> None:
    """首次即 AC（无连续 WA）：mastery 保持基线 1.0（回归保护）。"""
    user_id = uuid4()
    resp = await record_attempt(db_session, user_id, kp_single["kp"], kp_single["p"], "AC")
    assert resp.mastery == pytest.approx(1.0)
    assert resp.consecutive_wa == 0


# ===== 4. 时间衰减集成：recompute =====


async def test_recompute_applies_time_decay(db_session: AsyncSession, kp_single: dict[str, UUID]) -> None:
    """长期未活动的知识点，recompute 时 mastery 按遗忘曲线回落。"""
    user_id = uuid4()
    await record_attempt(db_session, user_id, kp_single["kp"], kp_single["p"], "AC")
    # 基线 1.0
    assert (await recompute_mastery_for_knowledge(db_session, user_id, kp_single["kp"])) == pytest.approx(1.0)

    # 回拨 30 天 → 衰减封底 0.5（30 > 7 + 1/0.05 = 27 天即到封底）
    await _backdate_state(db_session, user_id, kp_single["kp"], 30)
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_single["kp"])
    assert mastery == pytest.approx(1.0 * TIME_DECAY_FLOOR)

    # 衰减后的 mastery 写入 state
    state = (
        await db_session.execute(
            sa_select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == kp_single["kp"],
            )
        )
    ).scalar_one()
    assert state.mastery == pytest.approx(TIME_DECAY_FLOOR)
    # 0.5 < 0.5 不成立 → 不是 weak（保持原状态）
    assert state.is_weak is False


async def test_recompute_no_decay_when_active(db_session: AsyncSession, kp_single: dict[str, UUID]) -> None:
    """近期有活动的知识点 recompute 不衰减。"""
    user_id = uuid4()
    await record_attempt(db_session, user_id, kp_single["kp"], kp_single["p"], "AC")
    # 回拨 3 天（grace 内）→ 不衰减
    await _backdate_state(db_session, user_id, kp_single["kp"], 3)
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_single["kp"])
    assert mastery == pytest.approx(1.0)
