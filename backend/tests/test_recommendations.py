"""P1-1 推荐融合测试（Task 12 智能推送引擎）。

覆盖：
1. 薄弱知识点按 mastery 升序排序（越薄弱越靠前）
2. 无薄弱知识点返回空列表
3. 复习到期加权：同 mastery 下已到期复习的知识点优先
4. 错题重做优先：错题本中未解决的题排在同知识点普通题之前（优先于难度区间）
5. 题型偏好：与用户已 AC 题目标签重合的题优先
6. 难度区间匹配：贴近目标 rating 区间的题优先（优先于"简单优先"）
7. max_per_knowledge 截断
8. API 集成测试
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import Submission
from app.models.knowledge import KnowledgePoint
from app.models.learning import ReviewRecord, UserKnowledgeState, UserProblemAC
from app.models.problem import Problem, ProblemDifficulty, ProblemKnowledgePoint, ProblemStatus
from app.models.wrongbook import WrongBookEntry
from app.services.push import get_recommendations


@pytest.fixture
async def rec_env(db_session: AsyncSession) -> dict[str, UUID]:
    """构建推荐环境。

    - kp_a / kp_b 两个知识点
    - kp_a 关联 5 道已发布题（rating/tag 分布覆盖各信号）
    - kp_b 关联 2 道已发布题
    """
    suffix = uuid4().hex[:8]
    kp_a = KnowledgePoint(
        id=uuid4(),
        name=f"KP-A-{suffix}",
        slug=f"kp-a-{suffix}",
        description="a",
        order=-5000,
    )
    kp_b = KnowledgePoint(
        id=uuid4(),
        name=f"KP-B-{suffix}",
        slug=f"kp-b-{suffix}",
        description="b",
        order=-5001,
    )
    db_session.add_all([kp_a, kp_b])
    await db_session.flush()

    specs = [
        ("p_wrong", 1800.0, ["dp"], kp_a),  # 错题候选（rating 最高）
        ("p_tag", 1400.0, ["dp"], kp_a),  # 题型偏好候选
        ("p_band", 1300.0, ["math"], kp_a),  # 落在默认目标区间内
        ("p_far", 800.0, ["math"], kp_a),  # 远低于区间
        ("p_none", None, ["graphs"], kp_a),  # 未定级
        ("p_b1", 1000.0, ["dp"], kp_b),
        ("p_b2", 1500.0, ["math"], kp_b),
    ]
    problems: dict[str, UUID] = {}
    for i, (name, rating, tags, kp) in enumerate(specs):
        p = Problem(
            id=uuid4(),
            title=f"{name}",
            slug=f"{name}-{suffix}-{i}",
            description="test",
            difficulty=ProblemDifficulty.EASY,
            status=ProblemStatus.PUBLISHED,
            cf_rating=rating,
            cf_tags=tags,
        )
        db_session.add(p)
        db_session.add(ProblemKnowledgePoint(problem_id=p.id, knowledge_id=kp.id))
        problems[name] = p.id
    await db_session.flush()
    return {"kp_a": kp_a.id, "kp_b": kp_b.id, "problems": problems}


async def _set_weak(db_session: AsyncSession, user_id: UUID, kp_id: UUID, mastery: float) -> None:
    """为用户设置薄弱知识点状态。"""
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_id,
            mastery=mastery,
            is_weak=True,
            consecutive_wa=1,
        )
    )
    await db_session.flush()


# ===== 1. 薄弱知识点按 mastery 升序 =====


async def test_weak_sorted_by_mastery(db_session: AsyncSession, rec_env: dict[str, UUID]):
    """mastery 越低的知识点越靠前。"""
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.2)
    await _set_weak(db_session, user_id, rec_env["kp_b"], 0.4)

    resp = await get_recommendations(db_session, user_id)
    assert [it.knowledge_id for it in resp.items] == [rec_env["kp_a"], rec_env["kp_b"]]
    # 每个推荐项带理由与题目理由
    assert resp.items[0].reasons == ["薄弱知识点（掌握度 20%）"]
    assert resp.items[0].problems[0].reasons


# ===== 2. 无薄弱知识点返回空 =====


async def test_no_weak_returns_empty(db_session: AsyncSession, rec_env: dict[str, UUID]):
    user_id = uuid4()
    resp = await get_recommendations(db_session, user_id)
    assert resp.items == []


# ===== 3. 复习到期加权 =====


async def test_review_due_priority(db_session: AsyncSession, rec_env: dict[str, UUID]):
    """同 mastery 下，已到期复习的知识点优先。"""
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.4)
    await _set_weak(db_session, user_id, rec_env["kp_b"], 0.4)
    # kp_a 已到复习期
    db_session.add(
        ReviewRecord(
            user_id=user_id,
            knowledge_id=rec_env["kp_a"],
            next_review_at=datetime.now(UTC) - timedelta(hours=1),
            last_reviewed_at=datetime.now(UTC) - timedelta(days=2),
            review_count=1,
        )
    )
    await db_session.flush()

    resp = await get_recommendations(db_session, user_id)
    first = resp.items[0]
    assert first.knowledge_id == rec_env["kp_a"]
    assert first.review_due is True
    assert first.next_review_at is not None
    assert "复习到期" in first.reasons
    # 未到期的 kp_b 标记正确
    assert resp.items[1].review_due is False


# ===== 4. 错题重做优先 =====


async def test_wrongbook_problem_priority(db_session: AsyncSession, rec_env: dict[str, UUID]):
    """错题本中未解决的题（即使 rating 最高）排第一。"""
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.3)
    # 为 p_wrong 制造一条未解决错题记录（含 submission 外键）
    sub = Submission(
        cf_submission_id=uuid4().int % 10**15,
        user_id=user_id,
        problem_id=rec_env["problems"]["p_wrong"],
        contest_id=1,
        problem_index="A",
        handle_snapshot="tester",
        verdict="WA",
        programming_language="Python",
        submitted_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.flush()
    db_session.add(
        WrongBookEntry(
            user_id=user_id,
            submission_id=sub.id,
            problem_id=rec_env["problems"]["p_wrong"],
            verdict="WA",
            resolved=False,
        )
    )
    await db_session.flush()

    resp = await get_recommendations(db_session, user_id)
    first = resp.items[0].problems[0]
    assert first.problem_id == rec_env["problems"]["p_wrong"]
    assert "错题重做" in first.reasons


# ===== 5. 题型偏好 =====


async def test_tag_preference_priority(db_session: AsyncSession, rec_env: dict[str, UUID]):
    """与用户已 AC 题目标签重合的题，优先于无重合但更贴近区间的题。"""
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.3)
    # 用户已 AC 过一道带 ["dp"] 标签的题（该题本身不参与候选，仅贡献标签偏好）
    ref = Problem(
        id=uuid4(),
        title="AC 参考题",
        slug=f"ac-ref-{uuid4().hex[:8]}",
        description="ref",
        difficulty=ProblemDifficulty.MEDIUM,
        status=ProblemStatus.PUBLISHED,
        cf_rating=1500.0,
        cf_tags=["dp"],
    )
    db_session.add(ref)
    await db_session.flush()
    db_session.add(UserProblemAC(user_id=user_id, problem_id=ref.id))
    await db_session.flush()

    resp = await get_recommendations(db_session, user_id)
    first = resp.items[0].problems[0]
    # p_tag(dp, 1400) 优先于 p_band(math, 1300)：标签信号 > 区间距离
    assert first.problem_id == rec_env["problems"]["p_tag"]
    assert "题型偏好匹配" in first.reasons


# ===== 6. 难度区间匹配 =====


async def test_band_proximity_priority(db_session: AsyncSession, rec_env: dict[str, UUID]):
    """无错题/标签信号时，落在目标区间内的题优先于更简单的题。"""
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.3)

    resp = await get_recommendations(db_session, user_id, max_per_knowledge=5)
    ids = [p.problem_id for p in resp.items[0].problems]
    # p_band(1300 区间内) → p_tag(1400 区间内) → p_wrong(1800 距区间 200) → p_far(800 距区间 400) → p_none(None)
    expected = ["p_band", "p_tag", "p_wrong", "p_far", "p_none"]
    assert ids == [rec_env["problems"][name] for name in expected]
    assert "难度贴合目标区间" in resp.items[0].problems[0].reasons


# ===== 7. max_per_knowledge 截断 =====


async def test_max_per_knowledge_limit(db_session: AsyncSession, rec_env: dict[str, UUID]):
    user_id = uuid4()
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.3)

    resp = await get_recommendations(db_session, user_id, max_per_knowledge=2)
    assert len(resp.items[0].problems) == 2


# ===== 8. API 集成测试 =====


async def test_api_get_recommendations(
    client,
    db_session: AsyncSession,
    rec_env: dict[str, UUID],
    auth_user,
):
    """API: GET /api/v1/recommendations。"""
    user_id = auth_user["user"].id
    await _set_weak(db_session, user_id, rec_env["kp_a"], 0.3)

    resp = await client.get("/api/v1/recommendations", headers=auth_user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user_id)
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["knowledge_id"] == str(rec_env["kp_a"])
    assert item["mastery"] == 30
    assert "review_due" in item
    assert "reasons" in item
    assert item["problems"][0]["tags"]
