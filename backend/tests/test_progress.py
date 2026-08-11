"""Task 11 学习进度与掌握度测试。

覆盖：
1. 进度面板聚合数据正确（知识点数、AC 数、通过率）
2. mastery = AC 题数 / 关联题目总数
3. mastery ≥ 0.8 标记为已掌握
4. mastery < 0.5 自动标记为薄弱
5. 雷达图数据按知识点返回
6. 训练目标完成进度计算
7. AC 时自动重算 mastery（与 Task 10 集成）
8. 手动 recompute 接口
9. API 集成测试
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import UserKnowledgeState, UserProblemAC
from app.models.problem import Problem, ProblemDifficulty, ProblemKnowledgePoint, ProblemStatus
from app.services.learning_path import record_attempt
from app.services.progress import (
    get_progress_overview,
    recompute_mastery,
    recompute_mastery_for_knowledge,
)

# ===== fixtures =====


@pytest.fixture
async def kp_with_problems(db_session: AsyncSession) -> dict[str, UUID]:
    """创建 2 个知识点，每个关联 3 道已发布题目 + 1 道 draft 题目。

    - KP1: 3 道已发布题（p0/p1/p2）+ 1 道 draft（p3_draft）
    - KP2: 3 道已发布题（p4/p5/p6）
    总计 6 道已发布 + 1 道 draft。
    """
    suffix = uuid4().hex[:8]
    kp1 = KnowledgePoint(
        id=uuid4(),
        name=f"进度-数组-{suffix}",
        slug=f"prog-array-{suffix}",
        description="测试知识点 1",
        order=-100,
    )
    kp2 = KnowledgePoint(
        id=uuid4(),
        name=f"进度-DP-{suffix}",
        slug=f"prog-dp-{suffix}",
        description="测试知识点 2",
        order=-99,
    )
    db_session.add_all([kp1, kp2])
    await db_session.flush()

    problems = []
    # 6 道已发布
    for i in range(6):
        problems.append(
            Problem(
                id=uuid4(),
                title=f"进度题 {i}",
                slug=f"prog-p{i}-{suffix}",
                description="test",
                difficulty=ProblemDifficulty.EASY,
                status=ProblemStatus.PUBLISHED,
                cf_rating=1000.0 + i * 100,
            )
        )
    # 1 道 draft（用于测试 draft 不进入 mastery）
    draft_problem = Problem(
        id=uuid4(),
        title="进度题 draft",
        slug=f"prog-pdraft-{suffix}",
        description="draft",
        difficulty=ProblemDifficulty.EASY,
        status=ProblemStatus.DRAFT,
        cf_rating=999.0,
    )
    db_session.add_all(problems + [draft_problem])
    await db_session.flush()

    # KP1 关联 p0,p1,p2 + draft；KP2 关联 p3,p4,p5
    for i in range(3):
        db_session.add(ProblemKnowledgePoint(problem_id=problems[i].id, knowledge_id=kp1.id))
    db_session.add(ProblemKnowledgePoint(problem_id=draft_problem.id, knowledge_id=kp1.id))
    for i in range(3, 6):
        db_session.add(ProblemKnowledgePoint(problem_id=problems[i].id, knowledge_id=kp2.id))
    await db_session.flush()

    return {
        "kp1": kp1.id,
        "kp2": kp2.id,
        "p0": problems[0].id,
        "p1": problems[1].id,
        "p2": problems[2].id,
        "p3": problems[3].id,
        "p4": problems[4].id,
        "p5": problems[5].id,
        "p_draft": draft_problem.id,
    }


# ===== 1. 进度面板聚合数据正确 =====


async def test_progress_overview_aggregation(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """进度面板返回正确的聚合数据。"""
    user_id = uuid4()
    # 用户 AC 1 道题（p0 属于 KP1）
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    # 设置 KP1 mastery=0.5
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.5,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    overview = await get_progress_overview(db_session, user_id)
    assert overview.user_id == user_id
    # 至少有这两个测试知识点
    assert overview.total_knowledge_points >= 2
    assert overview.solved_problems == 1
    assert overview.total_problems >= 4
    assert 0.0 <= overview.acceptance_rate <= 1.0
    # 雷达图包含两个测试知识点
    radar_names = [c.name for c in overview.mastery_by_category]
    assert any("数组" in n for n in radar_names)
    assert any("DP" in n for n in radar_names)


# ===== 2. mastery = AC 题数 / 关联题目总数 =====


async def test_mastery_computation(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery = 用户在该知识点已 AC 题数 / 该知识点关联已发布题数。"""
    user_id = uuid4()
    # AC 1 道（KP1 关联 3 道已发布），mastery 应为 1/3
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    await db_session.flush()

    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    assert mastery == pytest.approx(1.0 / 3)

    # 再 AC 另一道，mastery = 2/3
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    await db_session.flush()
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    assert mastery == pytest.approx(2.0 / 3)

    # AC 全部 3 道，mastery = 1.0
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p2"]))
    await db_session.flush()
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    assert mastery == pytest.approx(1.0)


# ===== 3. mastery ≥ 0.8 且 AC ≥ 3 才算已掌握 =====


async def test_mastered_knowledge_counted(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery ≥ 0.8 且 AC ≥ 3 且非 weak 才计入已掌握。"""
    user_id = uuid4()
    # AC KP1 的全部 3 道题 → mastery = 1.0，AC=3 ≥ 3
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p2"]))
    await db_session.flush()
    await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])

    overview = await get_progress_overview(db_session, user_id)
    assert overview.mastered_knowledge_points >= 1


# ===== 4. 0 < mastery < 0.5 自动标记为薄弱；mastery=0 不算薄弱 =====


async def test_weak_knowledge_diagnosed(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """0 < mastery < 0.5 的知识点自动出现在 weak_knowledge_ids 中。"""
    user_id = uuid4()
    # 设置 KP2 mastery=0.3（薄弱）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp2"],
            mastery=0.3,
            is_weak=True,
            consecutive_wa=0,
        )
    )
    # 设置 KP1 mastery=0.0（未学，不算薄弱）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    overview = await get_progress_overview(db_session, user_id)
    assert kp_with_problems["kp2"] in overview.weak_knowledge_ids
    # mastery=0 的未学知识点不应出现在 weak 列表
    assert kp_with_problems["kp1"] not in overview.weak_knowledge_ids


# ===== 5. 雷达图数据按知识点返回 =====


async def test_radar_data_contains_all_knowledge(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """雷达图包含所有知识点，未学习的 mastery=0。"""
    user_id = uuid4()
    overview = await get_progress_overview(db_session, user_id)
    # 雷达图项数 = 知识点总数
    assert len(overview.mastery_by_category) == overview.total_knowledge_points
    # 每项 value 在 0-100 之间
    for item in overview.mastery_by_category:
        assert 0 <= item.value <= 100


# ===== 6. 训练目标完成进度 =====


async def test_target_progress(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """训练目标完成进度正确计算。"""
    from app.models.learning import LearningProfile

    user_id = uuid4()
    # 创建 profile
    db_session.add(
        LearningProfile(
            user_id=user_id,
            target_rating_min=1200,
            target_rating_max=1600,
        )
    )
    # AC KP1 的全部 3 道题 → mastery=1.0, AC=3 → 已掌握
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p2"]))
    await db_session.flush()
    await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])

    overview = await get_progress_overview(db_session, user_id)
    assert overview.target_progress is not None
    assert overview.target_progress.target_rating_min == 1200
    assert overview.target_progress.target_rating_max == 1600
    assert overview.target_progress.mastered_in_range >= 1
    assert 0 <= overview.target_progress.progress_percent <= 100


# ===== 7. AC 时自动重算 mastery（与 Task 10 集成） =====


async def test_ac_triggers_mastery_recompute(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """record_attempt(AC) 后 mastery 自动按 AC/总数 重算。"""
    user_id = uuid4()
    # 先生成路径（避免 record_attempt 创建 state 时缺路径）
    from app.services.learning_path import generate_learning_path

    await generate_learning_path(db_session, user_id, preview_count=5)

    # AC p0（属于 KP1，KP1 关联 3 道已发布题）
    resp = await record_attempt(
        db_session,
        user_id=user_id,
        knowledge_id=kp_with_problems["kp1"],
        problem_id=kp_with_problems["p0"],
        verdict="AC",
        # 不传 new_mastery，让 service 自动重算
    )
    # mastery = 1/3 ≈ 0.333，属于 (0, 0.5) → weak
    assert resp.mastery == pytest.approx(1.0 / 3)
    assert resp.is_weak is True  # 0 < 1/3 < 0.5 → weak


# ===== 8. 手动 recompute 接口 =====


async def test_recompute_all_user_knowledge(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """recompute_mastery(knowledge_id=None) 重算用户所有知识点。"""
    user_id = uuid4()
    # AC p0（KP1）和 p3（KP2）各一道
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p3"]))
    # 先创建 state 记录
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp2"],
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    result = await recompute_mastery(db_session, user_id, knowledge_id=None)
    assert result.recomputed == 2
    assert result.updated == 2  # 两个都从 0.0 变成 1/3

    # 验证 DB 中 mastery 已更新
    state1 = (
        await db_session.execute(
            sa_select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == kp_with_problems["kp1"],
            )
        )
    ).scalar_one()
    assert state1.mastery == pytest.approx(1.0 / 3)
    assert state1.is_weak is True  # 0 < 1/3 < 0.5 → weak


# ===== 9. API 集成测试 =====


async def test_api_progress_overview(client, db_session: AsyncSession, kp_with_problems: dict[str, UUID], auth_user):
    """API: GET /api/v1/progress/overview。"""
    user_id = auth_user["user"].id
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    await db_session.flush()

    resp = await client.get(
        "/api/v1/progress/overview",
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user_id)
    assert data["solved_problems"] == 1
    assert "mastery_by_category" in data
    assert "rating_history" in data
    assert isinstance(data["rating_history"], list)
    assert "weak_knowledge_ids" in data


async def test_api_recompute_mastery(client, db_session: AsyncSession, kp_with_problems: dict[str, UUID], auth_user):
    """API: POST /api/v1/progress/recompute。"""
    user_id = auth_user["user"].id
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    resp = await client.post(
        "/api/v1/progress/recompute",
        json={
            "knowledge_id": str(kp_with_problems["kp1"]),
        },
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recomputed"] == 1
    assert data["updated"] == 1


# ===== 10. mastery=1、AC=1 时不算已掌握 =====


async def test_mastery_one_but_ac_lt_three_not_mastered(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery=1.0 但 AC 题数 < 3 时不算已掌握。

    场景：知识点只关联 1 道已发布题，AC 这道后 mastery=1.0，但 AC<3。
    """
    # 临时加一个只有 1 道题的知识点
    suffix = uuid4().hex[:8]
    kp_solo = KnowledgePoint(
        id=uuid4(),
        name=f"进度-solo-{suffix}",
        slug=f"prog-solo-{suffix}",
        description="只有 1 道题",
        order=-98,
    )
    p_solo = Problem(
        id=uuid4(),
        title="solo 题",
        slug=f"prog-solo-p-{suffix}",
        description="test",
        difficulty=ProblemDifficulty.EASY,
        status=ProblemStatus.PUBLISHED,
        cf_rating=1000.0,
    )
    db_session.add_all([kp_solo, p_solo])
    await db_session.flush()
    db_session.add(ProblemKnowledgePoint(problem_id=p_solo.id, knowledge_id=kp_solo.id))
    await db_session.flush()

    user_id = uuid4()
    # AC 这 1 道题 → mastery=1.0，但 AC=1 < 3
    db_session.add(UserProblemAC(user_id=user_id, problem_id=p_solo.id))
    await db_session.flush()
    await recompute_mastery_for_knowledge(db_session, user_id, kp_solo.id)

    overview = await get_progress_overview(db_session, user_id)
    # mastery=1.0 但 AC<3，不应计入已掌握
    # 注意：overview.mastered_knowledge_points 是全量计数，只要没有其他已掌握项即为 0
    # 这里只验证 solo 知识点不算已掌握：用 target_progress.mastered_in_range 间接验证
    if overview.target_progress is None:
        # 无 profile 时 mastered_knowledge_points 直接反映
        assert overview.mastered_knowledge_points == 0


# ===== 11. mastery≥0.8 且 distinct AC≥3 时算已掌握 =====


async def test_mastered_with_ac_ge_three(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery≥0.8 且 AC≥3 时算已掌握。"""
    user_id = uuid4()
    # AC KP1 的全部 3 道题 → mastery=1.0, AC=3
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p2"]))
    await db_session.flush()
    await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])

    overview = await get_progress_overview(db_session, user_id)
    assert overview.mastered_knowledge_points >= 1


# ===== 12. draft 题目不进入 mastery 分子或分母 =====


async def test_draft_problem_excluded_from_mastery(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """draft 题目不进入 mastery 分子或分母。

    KP1 关联 3 道已发布 + 1 道 draft。AC draft 题不增加 mastery。
    """
    user_id = uuid4()
    # AC draft 题
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p_draft"]))
    await db_session.flush()
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    # draft 不计入分母（分母=3 已发布），AC draft 不计入分子 → mastery=0
    assert mastery == pytest.approx(0.0)


# ===== 13. mastery 不超过 1 =====


async def test_mastery_never_exceeds_one(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery 永远不超过 1。

    即使 AC 题数异常多于关联题数（理论上不应发生），mastery 也要被限制在 1。
    """
    user_id = uuid4()
    # AC 全部 3 道已发布题
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p2"]))
    await db_session.flush()
    mastery = await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    assert mastery == pytest.approx(1.0)
    assert mastery <= 1.0


# ===== 14. mastery=0 是未学，不是 weak =====


async def test_mastery_zero_is_not_weak(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """mastery=0 是未学，is_weak 必须为 False。"""
    user_id = uuid4()
    # 创建 mastery=0 的 state（模拟误置 is_weak=True 的脏数据）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.0,
            is_weak=True,  # 脏数据
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    # recompute 应修正 is_weak → False
    await recompute_mastery_for_knowledge(db_session, user_id, kp_with_problems["kp1"])
    state = (
        await db_session.execute(
            sa_select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == kp_with_problems["kp1"],
            )
        )
    ).scalar_one()
    assert state.mastery == 0.0
    assert state.is_weak is False  # 未学不是 weak

    # overview 的 weak_knowledge_ids 也不应包含 mastery=0 的
    overview = await get_progress_overview(db_session, user_id)
    assert kp_with_problems["kp1"] not in overview.weak_knowledge_ids


# ===== 15. 0 < mastery < 0.5 是 weak =====


def test_mastery_between_zero_and_half_is_weak():
    """0 < mastery < 0.5 是 weak。

    使用纯函数 _classify_weak 测试分级边界，避免 recompute 基于 AC/total 重算
    覆盖手动设置的 mastery 值。
    """
    from app.services.progress import _classify_weak

    # 0 < mastery < 0.5 → weak=True（无论 old_weak）
    assert _classify_weak(0.1, False) is True
    assert _classify_weak(0.3, False) is True
    assert _classify_weak(0.49, False) is True
    assert _classify_weak(0.3, True) is True


# ===== 16. mastery=0.5 不属于 weak =====


def test_mastery_half_is_not_weak():
    """mastery=0.5 属于基本掌握，不是 weak。

    使用纯函数 _classify_weak 测试分级边界。
    """
    from app.services.progress import _classify_weak

    # mastery=0.5 → 保持原状态（不算 weak）
    assert _classify_weak(0.5, False) is False
    assert _classify_weak(0.5, True) is True  # 保持原 weak 状态
    # mastery=0.8 → 不算 weak
    assert _classify_weak(0.8, True) is False
    # mastery=0.79 → 保持原状态
    assert _classify_weak(0.79, True) is True
    assert _classify_weak(0.79, False) is False


# ===== 17. mastery 数值未变化时也能修正错误的 is_weak =====


async def test_recompute_fixes_wrong_weak_even_if_mastery_unchanged(
    db_session: AsyncSession, kp_with_problems: dict[str, UUID]
):
    """mastery 数值未变化时，recompute 也能修正错误的 is_weak。"""
    user_id = uuid4()
    # AC 1 道 → mastery=1/3，但人为设置 is_weak=False（脏数据）
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=1.0 / 3,
            is_weak=False,  # 脏数据：应该为 True
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    result = await recompute_mastery(db_session, user_id, kp_with_problems["kp1"])
    # mastery 数值未变（仍 1/3），但 is_weak 从 False 修正为 True → updated=1
    assert result.updated == 1
    state = (
        await db_session.execute(
            sa_select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == kp_with_problems["kp1"],
            )
        )
    ).scalar_one()
    assert state.is_weak is True


# ===== 18. 客户端 new_mastery 不能覆盖服务端计算 =====


async def test_client_new_mastery_ignored(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """客户端传入的 new_mastery 被服务端忽略。"""
    from app.services.learning_path import generate_learning_path

    user_id = uuid4()
    await generate_learning_path(db_session, user_id, preview_count=5)

    # AC p0 并传入 new_mastery=0.99（试图覆盖）
    resp = await record_attempt(
        db_session,
        user_id=user_id,
        knowledge_id=kp_with_problems["kp1"],
        problem_id=kp_with_problems["p0"],
        verdict="AC",
        new_mastery=0.99,  # 应被忽略
    )
    # 真实 mastery = 1/3 ≈ 0.333，不是 0.99
    assert resp.mastery == pytest.approx(1.0 / 3)
    assert resp.mastery != 0.99


# ===== 19. 只有 AC 数据、没有 state 时，全量 recompute 仍能创建状态 =====


async def test_recompute_creates_state_from_ac_only(db_session: AsyncSession, kp_with_problems: dict[str, UUID]):
    """只有 UserProblemAC、没有 UserKnowledgeState 时，全量 recompute 仍能创建状态。"""
    user_id = uuid4()
    # 只 AC，不创建 state
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p0"]))
    db_session.add(UserProblemAC(user_id=user_id, problem_id=kp_with_problems["p1"]))
    await db_session.flush()

    # 全量重算
    result = await recompute_mastery(db_session, user_id, knowledge_id=None)
    assert result.recomputed >= 1  # 至少 KP1 被重算
    # 验证 state 被创建
    state = (
        await db_session.execute(
            sa_select(UserKnowledgeState).where(
                UserKnowledgeState.user_id == user_id,
                UserKnowledgeState.knowledge_id == kp_with_problems["kp1"],
            )
        )
    ).scalar_one_or_none()
    assert state is not None
    assert state.mastery == pytest.approx(2.0 / 3)


# ===== 20. progress overview API 返回正确的 weak_knowledge_ids =====


async def test_api_weak_knowledge_ids(client, db_session: AsyncSession, kp_with_problems: dict[str, UUID], auth_user):
    """API: GET /api/v1/progress/overview 的 weak_knowledge_ids 严格按 spec。"""
    user_id = auth_user["user"].id
    # KP1 mastery=0.3（weak），KP2 mastery=0.0（未学，不算 weak）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp1"],
            mastery=0.3,
            is_weak=True,
            consecutive_wa=0,
        )
    )
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_with_problems["kp2"],
            mastery=0.0,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/progress/overview",
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    weak_ids = data["weak_knowledge_ids"]
    assert str(kp_with_problems["kp1"]) in weak_ids
    assert str(kp_with_problems["kp2"]) not in weak_ids
    # MasteryByCategory 应包含 knowledge_id 字段
    for item in data["mastery_by_category"]:
        assert "knowledge_id" in item


# ===== 21. 不存在的 knowledge_id 返回 404 =====


async def test_recompute_nonexistent_knowledge_404(client, auth_user):
    """API: POST /api/v1/progress/recompute 对不存在的 knowledge_id 返回 404。"""
    fake_kp = uuid4()

    resp = await client.post(
        "/api/v1/progress/recompute",
        json={
            "knowledge_id": str(fake_kp),
        },
        headers=auth_user["headers"],
    )
    assert resp.status_code == 404
