"""Task 9 冷启动测试（诊断题冷启动）。

覆盖：
1. diagnostic_cold_start 选 15 题：5 易 + 7 中 + 3 难，题目不重复
2. 无平台已发布题时不崩溃，返回空诊断列表
3. 诊断冷启动写入默认训练目标 1200-1600
4. API 集成：POST /api/v1/coldstart/diagnostic
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint
from app.models.learning import LearningProfile
from app.models.problem import Problem, ProblemDifficulty, ProblemKnowledgePoint, ProblemSource, ProblemStatus
from app.services.coldstart import diagnostic_cold_start


@pytest.fixture
async def diag_env(db_session: AsyncSession) -> dict[str, UUID]:
    """3 个知识点，每个关联 3 道已发布的 platform 题 × 3 种难度（共 27 题）。

    order 设为 -5000 级别，确保在按 order 排序的核心知识点选择中排最前。
    """
    suffix = uuid4().hex[:8]
    kps: list[KnowledgePoint] = []
    for i in range(3):
        kps.append(
            KnowledgePoint(
                id=uuid4(),
                name=f"诊断-{i}-{suffix}",
                slug=f"diag-{i}-{suffix}",
                description="test",
                order=-5000 + i,
            )
        )
    db_session.add_all(kps)
    await db_session.flush()

    problems: list[Problem] = []
    pairs: list[tuple[UUID, UUID]] = []  # (kp_id, problem_id)
    for kp in kps:
        for difficulty in (ProblemDifficulty.EASY, ProblemDifficulty.MEDIUM, ProblemDifficulty.HARD):
            for j in range(3):
                p = Problem(
                    id=uuid4(),
                    title=f"{kp.slug}-{difficulty.value}-{j}",
                    slug=f"{kp.slug}-{difficulty.value}-{j}-{uuid4().hex[:6]}",
                    description="test",
                    difficulty=difficulty,
                    status=ProblemStatus.PUBLISHED,
                    source=ProblemSource.PLATFORM,
                    cf_rating=None,
                )
                problems.append(p)
                pairs.append((kp.id, p.id))
    db_session.add_all(problems)
    await db_session.flush()
    db_session.add_all([ProblemKnowledgePoint(problem_id=pid, knowledge_id=kid) for kid, pid in pairs])
    await db_session.flush()
    return {"kps": kps, "problems": problems}


async def _problem_difficulties(db_session: AsyncSession, problem_ids: list[UUID]) -> dict[UUID, str]:
    rows = (
        await db_session.execute(sa_select(Problem.id, Problem.difficulty).where(Problem.id.in_(problem_ids)))
    ).all()
    return {pid: d.value for pid, d in rows}


# ===== 1. 诊断题 5 易 + 7 中 + 3 难，共 15 题且不重复 =====


async def test_diagnostic_selects_15_cover_all_difficulties(db_session: AsyncSession, diag_env: dict[str, UUID]):
    user_id = uuid4()
    result = await diagnostic_cold_start(db_session, user_id)

    assert result.method == "diagnostic"
    assert len(result.diagnostic_problems) == 15
    assert len(set(result.diagnostic_problems)) == 15  # 不重复

    diff_map = await _problem_difficulties(db_session, result.diagnostic_problems)
    counts: dict[str, int] = {}
    for pid in result.diagnostic_problems:
        counts[diff_map[pid]] = counts.get(diff_map[pid], 0) + 1
    assert counts == {"easy": 5, "medium": 7, "hard": 3}

    # 覆盖核心知识点（next_available_count 至少 3）
    assert result.next_available_count >= 3
    assert result.target_rating_min == 1200
    assert result.target_rating_max == 1600


# ===== 2. 无平台已发布题时不崩溃 =====


async def test_diagnostic_no_problems_returns_empty(db_session: AsyncSession):
    user_id = uuid4()
    result = await diagnostic_cold_start(db_session, user_id)

    # 不崩溃：返回空诊断列表与默认目标
    assert result.method == "diagnostic"
    assert result.diagnostic_problems == []
    assert result.target_rating_min == 1200
    assert result.target_rating_max == 1600


# ===== 3. 诊断冷启动写入默认训练目标 =====


async def test_diagnostic_creates_default_profile(db_session: AsyncSession, diag_env: dict[str, UUID]):
    user_id = uuid4()
    await diagnostic_cold_start(db_session, user_id)

    profile = (
        await db_session.execute(sa_select(LearningProfile).where(LearningProfile.user_id == user_id))
    ).scalar_one()
    assert (profile.target_rating_min, profile.target_rating_max) == (1200, 1600)


# ===== 4. API 集成测试 =====


async def test_api_diagnostic_cold_start(
    client,
    db_session: AsyncSession,
    diag_env: dict[str, UUID],
    auth_user,
):
    resp = await client.post("/api/v1/coldstart/diagnostic", headers=auth_user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["method"] == "diagnostic"
    assert data["target_rating_min"] == 1200
    assert data["target_rating_max"] == 1600
    assert isinstance(data["diagnostic_problems"], list)
    assert len(data["diagnostic_problems"]) == 15
