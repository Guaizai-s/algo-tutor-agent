"""Task 10 学习路径与推送引擎测试。

覆盖：
1. DAG 拓扑顺序正确
2. 已掌握节点被跳过
3. weak 节点被保留
4. 环检测返回明确错误
5. 连续 3 次 WA 插入一次补漏项
6. 第 4 次 WA 不重复插入
7. AC 重置连续 WA
8. 推荐题目按 cf_rating 升序
9. 已 AC 题目被排除
10. 不同 rating 槽位选择正确
11. 当日计划生成内容正确
12. 同日重复请求幂等
13. 候选不足返回 missing_slots
14. API 集成测试覆盖路径生成和今日任务
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePoint, KnowledgePrerequisite, Lecture, LectureLevel
from app.models.learning import (
    UserKnowledgeState,
    UserProblemAC,
)
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.services.daily_tasks import get_or_create_today_task
from app.services.learning_path import (
    CycleDetectedError,
    generate_learning_path,
    get_current_learning_path,
    record_attempt,
    topological_sort,
)
from app.services.recommendation import recommend_for_slots

# ===== fixtures =====


@pytest.fixture
async def kp_chain(db_session: AsyncSession) -> dict[str, UUID]:
    """构建 5 个知识点的链式 DAG: A -> B -> C -> D -> E（前置依赖链）。

    A 是 B 的前置，B 是 C 的前置，以此类推。
    name/slug 带 uuid 后缀避免跨测试唯一约束冲突。
    依赖 conftest 的 session.begin() 事务在测试结束时整体回滚，
    不再使用 raw DELETE 清理表（避免与 conftest 事务隔离冲突）。

    注意：测试用知识点 order 设为负数，确保拓扑排序时排最前
    （避免被 DB seed 知识点挤掉预览窗口）。
    """
    suffix = uuid4().hex[:8]
    ids = {name: uuid4() for name in "ABCDE"}
    kps = []
    for name, kid in ids.items():
        kps.append(
            KnowledgePoint(
                id=kid,
                name=f"KP-{name}-{suffix}",
                slug=f"kp-{name.lower()}-{suffix}",
                description=f"知识点 {name}",
                # order 设为负数确保拓扑排序时排最前（避免被 DB seed 知识点挤掉）
                order=-10000 + ord(name),
            )
        )
    db_session.add_all(kps)
    await db_session.flush()

    # 依赖链 A -> B -> C -> D -> E
    edges = [
        (ids["A"], ids["B"]),
        (ids["B"], ids["C"]),
        (ids["C"], ids["D"]),
        (ids["D"], ids["E"]),
    ]
    for prereq_id, kid in edges:
        db_session.add(KnowledgePrerequisite(knowledge_id=kid, prerequisite_id=prereq_id))
    await db_session.flush()
    return ids


@pytest.fixture
async def problems_with_rating(db_session: AsyncSession, kp_chain: dict[str, UUID]) -> dict[str, UUID]:
    """为知识点 C 创建 6 道已发布题目，rating 分布：
    - 2 道 rating 1000（模板题候选）
    - 2 道 rating 1400（应用题候选）
    - 2 道 rating 1800（挑战题候选）
    - 1 道 rating NULL（未定级，不混入 rating 槽位）
    """
    kp_c = kp_chain["C"]
    problems = []
    ratings = [1000.0, 1000.0, 1400.0, 1400.0, 1800.0, 1800.0, None]
    for i, r in enumerate(ratings):
        problems.append(
            Problem(
                id=uuid4(),
                title=f"题 C-{i}",
                slug=f"problem-c-{i}-{uuid4().hex[:8]}",
                description="test",
                difficulty=ProblemDifficulty.EASY,
                status=ProblemStatus.PUBLISHED,
                cf_rating=r,
            )
        )
    db_session.add_all(problems)
    await db_session.flush()

    for p in problems:
        from app.models.problem import ProblemKnowledgePoint

        db_session.add(ProblemKnowledgePoint(problem_id=p.id, knowledge_id=kp_c))
    await db_session.flush()

    return {f"p{i}": p.id for i, p in enumerate(problems)}


@pytest.fixture
async def card_lecture(db_session: AsyncSession, kp_chain: dict[str, UUID]) -> UUID:
    """为知识点 C 添加一个 CARD 讲义。"""
    lecture = Lecture(
        id=uuid4(),
        knowledge_id=kp_chain["C"],
        level=LectureLevel.CARD,
        title="CARD 讲义",
        content="这是知识卡片。",
    )
    db_session.add(lecture)
    await db_session.flush()
    return lecture.id


# ===== 1. DAG 拓扑顺序正确 =====


def test_topological_sort_chain():
    """链式 DAG 拓扑排序后，前置必在后继之前。

    纯算法同步测试，不使用 async / db_session / kp_chain fixture，
    避免 event_loop 跨测试复用导致 asyncpg 连接池污染。
    """
    from app.models.knowledge import KnowledgePoint

    ids = {name: uuid4() for name in "ABCDE"}
    kp_map = {
        ids["A"]: KnowledgePoint(id=ids["A"], name="KP-A", slug="a", order=0),
        ids["B"]: KnowledgePoint(id=ids["B"], name="KP-B", slug="b", order=0),
        ids["C"]: KnowledgePoint(id=ids["C"], name="KP-C", slug="c", order=0),
        ids["D"]: KnowledgePoint(id=ids["D"], name="KP-D", slug="d", order=0),
        ids["E"]: KnowledgePoint(id=ids["E"], name="KP-E", slug="e", order=0),
    }
    adj = {
        ids["A"]: [ids["B"]],
        ids["B"]: [ids["C"]],
        ids["C"]: [ids["D"]],
        ids["D"]: [ids["E"]],
    }
    topo = topological_sort(kp_map, adj)
    # A 必须在 B 之前，B 在 C 之前，以此类推
    pos = {kid: i for i, kid in enumerate(topo)}
    assert pos[ids["A"]] < pos[ids["B"]]
    assert pos[ids["B"]] < pos[ids["C"]]
    assert pos[ids["C"]] < pos[ids["D"]]
    assert pos[ids["D"]] < pos[ids["E"]]


# ===== 2. 已掌握节点被跳过 =====


async def test_mastered_node_skipped(db_session: AsyncSession, kp_chain: dict[str, UUID]):
    """mastery ≥ 0.8 的节点在路径中被跳过。"""
    user_id = uuid4()
    # 标记 A、B 为已掌握
    for name in ("A", "B"):
        db_session.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=kp_chain[name],
                mastery=0.9,
                is_weak=False,
                consecutive_wa=0,
            )
        )
    await db_session.flush()

    path = await generate_learning_path(db_session, user_id, preview_count=5)
    knowledge_ids = [it.knowledge_id for it in path.items]
    # A、B 应被跳过
    assert kp_chain["A"] not in knowledge_ids
    assert kp_chain["B"] not in knowledge_ids
    # C、D、E 应在路径中
    assert kp_chain["C"] in knowledge_ids
    assert kp_chain["D"] in knowledge_ids
    assert kp_chain["E"] in knowledge_ids


# ===== 3. weak 节点被保留 =====


async def test_weak_node_kept_as_remediation(db_session: AsyncSession, kp_chain: dict[str, UUID]):
    """weak 节点必须保留且 kind=remediation。"""
    user_id = uuid4()
    # 标记 C 为已掌握但 weak（仍需保留）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            mastery=0.9,
            is_weak=True,
            consecutive_wa=5,
        )
    )
    await db_session.flush()

    path = await generate_learning_path(db_session, user_id, preview_count=5)
    c_item = next(it for it in path.items if it.knowledge_id == kp_chain["C"])
    from app.models.learning import PathItemKind

    assert c_item.kind == PathItemKind.REMEDIATION


# ===== 4. 环检测返回明确错误 =====


def test_cycle_detection():
    """图中存在环时抛 CycleDetectedError。

    纯算法同步测试，不使用 async / db_session / fixture。
    """
    from app.models.knowledge import KnowledgePoint

    ids = {name: uuid4() for name in "ABC"}
    kp_map = {
        ids["A"]: KnowledgePoint(id=ids["A"], name="A", slug="a", order=0),
        ids["B"]: KnowledgePoint(id=ids["B"], name="B", slug="b", order=0),
        ids["C"]: KnowledgePoint(id=ids["C"], name="C", slug="c", order=0),
    }
    adj = {
        ids["A"]: [ids["B"]],
        ids["B"]: [ids["C"]],
        ids["C"]: [ids["A"]],
    }
    with pytest.raises(CycleDetectedError):
        topological_sort(kp_map, adj)


# ===== 5. 连续 3 次 WA 插入一次补漏项 =====


async def test_consecutive_wa_inserts_remediation(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """连续 WA 3 次触发补漏插入。

    设 mastery=0.6（>WEAK_MASTERY_THRESHOLD=0.5），避免 mastery 条件提前触发 weak。
    这样只有 consecutive_wa >= 3 才会触发。
    """
    user_id = uuid4()
    # 先生成路径
    await generate_learning_path(db_session, user_id, preview_count=5)
    # 设置初始 mastery=0.6（避免 mastery<0.5 提前触发 weak）
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            mastery=0.6,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    # 连续 3 次 WA
    for _ in range(3):
        resp = await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating["p0"],
            verdict="WA",
        )
    assert resp.is_weak is True
    # 第三次时应已插入补漏
    # 注意：前两次 is_weak=False 不插入，第三次 is_weak=True 才插入
    assert resp.remediation_inserted is True

    # 验证路径中 C 的 kind 改为 remediation
    path = await get_current_learning_path(db_session, user_id)
    from app.models.learning import PathItemKind

    c_item = next(it for it in path.items if it.knowledge_id == kp_chain["C"])
    assert c_item.kind == PathItemKind.REMEDIATION


# ===== 6. 第 4 次 WA 不重复插入 =====


async def test_fourth_wa_no_duplicate(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """第 4 次 WA 不重复插入相同补漏项。"""
    user_id = uuid4()
    await generate_learning_path(db_session, user_id, preview_count=5)
    # mastery=0.6 避免 mastery<0.5 提前触发 weak
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            mastery=0.6,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    # 3 次 WA → 插入补漏
    for _ in range(3):
        resp3 = await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating["p0"],
            verdict="WA",
        )
    assert resp3.remediation_inserted is True

    # 第 4 次 WA → 不重复插入
    resp4 = await record_attempt(
        db_session,
        user_id=user_id,
        knowledge_id=kp_chain["C"],
        problem_id=problems_with_rating["p0"],
        verdict="WA",
    )
    assert resp4.remediation_inserted is False
    assert resp4.consecutive_wa == 4


# ===== 7. AC 重置连续 WA =====


async def test_ac_resets_consecutive_wa(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """AC 后 consecutive_wa 归零。"""
    user_id = uuid4()
    await generate_learning_path(db_session, user_id, preview_count=5)
    # mastery=0.6 避免 mastery<0.5 提前触发 weak
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            mastery=0.6,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()

    # 2 次 WA
    for _ in range(2):
        await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating["p0"],
            verdict="WA",
        )
    # AC C 的 6 道题 → mastery=6/7≈0.857 ≥ 0.8 清除 weak（C 关联 7 道已发布题）
    # Task 11: new_mastery 被忽略，mastery 由 AC/总数 计算。
    for i in range(6):
        resp = await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating[f"p{i}"],
            verdict="AC",
        )
    assert resp.consecutive_wa == 0
    assert resp.is_weak is False  # mastery ≥ 0.8 清除 weak


# ===== 8. 推荐题目按 cf_rating 升序 =====


async def test_recommend_problems_sorted_by_rating(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """推荐题目按 cf_rating 升序。"""
    user_id = uuid4()
    template, application, challenge, _no_rating, _profile = await recommend_for_slots(
        db_session, user_id, kp_chain["C"]
    )
    # 模板题应按 rating 升序
    template_ratings = [p.cf_rating for p in template]
    assert template_ratings == sorted(template_ratings)
    # 所有模板题 rating <= 1200（默认 target_min）
    assert all(r <= 1200 for r in template_ratings)


# ===== 9. 已 AC 题目被排除 =====


async def test_ac_problems_excluded(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """已 AC 的题目从推荐中排除。"""
    user_id = uuid4()
    # 标记 p0 为已 AC
    db_session.add(UserProblemAC(user_id=user_id, problem_id=problems_with_rating["p0"]))
    await db_session.flush()

    template, _app, _chal, _nr, _prof = await recommend_for_slots(db_session, user_id, kp_chain["C"])
    template_ids = {p.id for p in template}
    assert problems_with_rating["p0"] not in template_ids


# ===== 10. 不同 rating 槽位选择正确 =====


async def test_rating_slots_correct(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """模板题 rating <= min, 应用题 min<=r<=max, 挑战题 r>=max。"""
    user_id = uuid4()
    template, application, challenge, no_rating, _profile = await recommend_for_slots(
        db_session, user_id, kp_chain["C"]
    )
    tmin = float(_profile.target_rating_min)  # 1200
    tmax = float(_profile.target_rating_max)  # 1600

    for p in template:
        assert p.cf_rating is not None
        assert p.cf_rating <= tmin
    for p in application:
        assert p.cf_rating is not None
        assert tmin <= p.cf_rating <= tmax
    for p in challenge:
        assert p.cf_rating is not None
        assert p.cf_rating >= tmax
    # 未定级题不混入 rating 槽位
    for p in no_rating:
        assert p.cf_rating is None
    # rating 槽位中不应有 None rating
    for p in template + application + challenge:
        assert p.cf_rating is not None


# ===== 11. 当日计划生成内容正确 =====


async def test_daily_task_content(
    db_session: AsyncSession,
    kp_chain: dict[str, UUID],
    problems_with_rating: dict[str, UUID],
    card_lecture: UUID,
):
    """当日任务包含：1 CARD 讲义 + 1 模板题 + 2 应用题 + 1 挑战题。"""
    user_id = uuid4()
    # 标记 A、B 为已掌握，使 C 成为路径第一个节点（当日任务目标）
    for name in ("A", "B"):
        db_session.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=kp_chain[name],
                mastery=0.9,
                is_weak=False,
                consecutive_wa=0,
            )
        )
    await db_session.flush()
    await generate_learning_path(db_session, user_id, preview_count=5)

    resp = await get_or_create_today_task(db_session, user_id)
    from app.models.learning import DailyTaskItemType

    item_types = [it.item_type for it in resp.task.items]
    assert item_types.count(DailyTaskItemType.LECTURE_CARD) == 1
    assert item_types.count(DailyTaskItemType.TEMPLATE_PROBLEM) == 1
    assert item_types.count(DailyTaskItemType.APPLICATION_PROBLEM) == 2
    assert item_types.count(DailyTaskItemType.CHALLENGE_PROBLEM) == 1
    # 无缺失
    assert resp.task.missing_slots == []


# ===== 12. 同日重复请求幂等 =====


async def test_daily_task_idempotent(
    db_session: AsyncSession,
    kp_chain: dict[str, UUID],
    problems_with_rating: dict[str, UUID],
    card_lecture: UUID,
):
    """同日重复请求返回同一份计划。"""
    user_id = uuid4()
    # 标记 A、B 为已掌握，使 C 成为路径第一个节点
    for name in ("A", "B"):
        db_session.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=kp_chain[name],
                mastery=0.9,
                is_weak=False,
                consecutive_wa=0,
            )
        )
    await db_session.flush()
    await generate_learning_path(db_session, user_id, preview_count=5)

    resp1 = await get_or_create_today_task(db_session, user_id)
    resp2 = await get_or_create_today_task(db_session, user_id)
    assert resp1.task.id == resp2.task.id
    assert [it.id for it in resp1.task.items] == [it.id for it in resp2.task.items]


# ===== 13. 候选不足返回 missing_slots =====


async def test_missing_slots_when_no_problems(db_session: AsyncSession, kp_chain: dict[str, UUID], card_lecture: UUID):
    """无题目候选时返回 missing_slots，不抛 500。"""
    user_id = uuid4()
    # 标记 A、B 为已掌握，使 C 成为路径第一个节点（C 有 CARD 讲义但无题目）
    for name in ("A", "B"):
        db_session.add(
            UserKnowledgeState(
                user_id=user_id,
                knowledge_id=kp_chain[name],
                mastery=0.9,
                is_weak=False,
                consecutive_wa=0,
            )
        )
    await db_session.flush()
    await generate_learning_path(db_session, user_id, preview_count=5)

    resp = await get_or_create_today_task(db_session, user_id)
    from app.models.learning import DailyTaskItemType

    # 模板题、应用题、挑战题都应缺失（CARD 讲义存在）
    assert DailyTaskItemType.TEMPLATE_PROBLEM.value in resp.task.missing_slots
    assert DailyTaskItemType.APPLICATION_PROBLEM.value in resp.task.missing_slots
    assert DailyTaskItemType.CHALLENGE_PROBLEM.value in resp.task.missing_slots
    # CARD 讲义不缺失
    assert DailyTaskItemType.LECTURE_CARD.value not in resp.task.missing_slots


# ===== 14. API 集成测试 =====


async def test_api_generate_path(client, db_session: AsyncSession, kp_chain: dict[str, UUID]):
    """API: POST /api/v1/learning-paths/generate。"""
    user_id = uuid4()
    resp = await client.post(
        "/api/v1/learning-paths/generate",
        json={"user_id": str(user_id), "preview_count": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user_id)
    assert data["is_active"] is True
    assert len(data["items"]) == 5


async def test_api_get_today_task(
    client,
    db_session: AsyncSession,
    kp_chain: dict[str, UUID],
    problems_with_rating: dict[str, UUID],
    card_lecture: UUID,
):
    """API: GET /api/v1/daily-tasks/today。"""
    user_id = uuid4()
    # 先生成路径
    gen_resp = await client.post(
        "/api/v1/learning-paths/generate",
        json={"user_id": str(user_id), "preview_count": 5},
    )
    assert gen_resp.status_code == 200

    # 获取今日任务
    resp = await client.get(
        "/api/v1/daily-tasks/today",
        params={"user_id": str(user_id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task" in data
    assert "path_preview" in data
    assert len(data["task"]["items"]) == 5


async def test_api_today_task_404_without_path(client):
    """API: 无路径时 GET /api/v1/daily-tasks/today 返回 404。"""
    user_id = uuid4()
    resp = await client.get(
        "/api/v1/daily-tasks/today",
        params={"user_id": str(user_id)},
    )
    assert resp.status_code == 404


# ===== 15. 新用户第一次 WA 不触发补漏 =====


async def test_first_wa_does_not_trigger_remediation(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """新用户 mastery=0.0 默认值，第一次 WA 不应触发 weak/补漏。

    回归 P1 修复：mastery<0.5 不再作为 weak 触发条件。
    """
    user_id = uuid4()
    await generate_learning_path(db_session, user_id, preview_count=5)
    # 不预设 mastery，使用默认值 0.0
    resp = await record_attempt(
        db_session,
        user_id=user_id,
        knowledge_id=kp_chain["C"],
        problem_id=problems_with_rating["p0"],
        verdict="WA",
    )
    assert resp.consecutive_wa == 1
    assert resp.is_weak is False  # 第一次 WA 不触发 weak
    assert resp.remediation_inserted is False


# ===== 16. AC 写入 UserProblemAC 并标记路径项 DONE =====


async def test_ac_writes_user_problem_ac_and_marks_done(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """AC 后：
    1. 写入 UserProblemAC（推荐会排除已 AC 题目）
    2. mastery ≥ 0.8 时把对应路径项标记为 DONE
    3. 解锁后续 pending 项为 active

    注意：Task 11 后 mastery 由 AC 题数/关联总数 计算，客户端 new_mastery 被忽略。
    本测试为 A 创建 3 道已发布题并 AC 全部，使 mastery=1.0、AC=3。
    """
    from sqlalchemy import select as sa_select

    from app.models.learning import LearningPathItem, PathItemStatus, UserProblemAC
    from app.models.problem import ProblemKnowledgePoint

    user_id = uuid4()
    # 为 A 创建 3 道已发布题（复用 problems_with_rating 的题，关联到 A）
    for i in range(3):
        db_session.add(ProblemKnowledgePoint(problem_id=problems_with_rating[f"p{i}"], knowledge_id=kp_chain["A"]))
    await db_session.flush()

    # 链 A->B->C->D->E：A 是 B 前置，A 未掌握时 B 是 pending
    await generate_learning_path(db_session, user_id, preview_count=5)
    path = await get_current_learning_path(db_session, user_id)
    a_item = next(it for it in path.items if it.knowledge_id == kp_chain["A"])
    b_item = next(it for it in path.items if it.knowledge_id == kp_chain["B"])
    assert a_item.status == PathItemStatus.ACTIVE
    assert b_item.status == PathItemStatus.PENDING

    # AC A 的 3 道题 → mastery=3/3=1.0 ≥ 0.8，AC=3 ≥ 3
    for i in range(3):
        resp = await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["A"],
            problem_id=problems_with_rating[f"p{i}"],
            verdict="AC",
        )
    assert resp.consecutive_wa == 0
    assert resp.is_weak is False
    assert resp.mastery == pytest.approx(1.0)

    # 1) UserProblemAC 应有 3 条记录
    ac_count = (
        await db_session.execute(
            sa_select(func.count()).select_from(UserProblemAC).where(UserProblemAC.user_id == user_id)
        )
    ).scalar_one()
    assert ac_count >= 3

    # 2) A 的路径项应标记为 DONE
    a_item_db = (
        await db_session.execute(sa_select(LearningPathItem).where(LearningPathItem.id == a_item.id))
    ).scalar_one()
    assert a_item_db.status == PathItemStatus.DONE

    # 3) B 应从 pending 解锁为 active
    b_item_db = (
        await db_session.execute(sa_select(LearningPathItem).where(LearningPathItem.id == b_item.id))
    ).scalar_one()
    assert b_item_db.status == PathItemStatus.ACTIVE


# ===== 17. AC 后补漏项恢复为 normal =====


async def test_ac_restores_remediation_to_normal(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """AC 且 mastery 提升后，原补漏项 kind 从 remediation 恢复为 normal。"""
    from sqlalchemy import select as sa_select

    from app.models.learning import LearningPathItem, PathItemKind

    user_id = uuid4()
    # 先制造 weak + 补漏
    db_session.add(
        UserKnowledgeState(
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            mastery=0.6,
            is_weak=False,
            consecutive_wa=0,
        )
    )
    await db_session.flush()
    await generate_learning_path(db_session, user_id, preview_count=5)
    for _ in range(3):
        await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating["p0"],
            verdict="WA",
        )
    # 现在 C 应是 remediation
    path = await get_current_learning_path(db_session, user_id)
    c_item = next(it for it in path.items if it.knowledge_id == kp_chain["C"])
    assert c_item.kind == PathItemKind.REMEDIATION

    # AC C 的 6 道题 → mastery=6/7≈0.857 ≥ 0.8（C 关联 7 道已发布题）
    # Task 11: mastery 由 AC/总数 计算，客户端 new_mastery 被忽略。
    for i in range(6):
        await record_attempt(
            db_session,
            user_id=user_id,
            knowledge_id=kp_chain["C"],
            problem_id=problems_with_rating[f"p{i}"],
            verdict="AC",
        )
    # C 的 kind 应恢复为 normal
    c_item_db = (
        await db_session.execute(sa_select(LearningPathItem).where(LearningPathItem.id == c_item.id))
    ).scalar_one()
    assert c_item_db.kind == PathItemKind.NORMAL


# ===== 18. AC 后题目从推荐中排除（业务闭环） =====


async def test_ac_recorded_then_excluded_from_recommendation(
    db_session: AsyncSession, kp_chain: dict[str, UUID], problems_with_rating: dict[str, UUID]
):
    """record_attempt AC 后，该题目从后续 recommend_for_slots 中排除。"""
    user_id = uuid4()
    # AC p0（属于 C）。Task 11: new_mastery 被忽略，mastery 由 AC/总数 计算。
    await record_attempt(
        db_session,
        user_id=user_id,
        knowledge_id=kp_chain["C"],
        problem_id=problems_with_rating["p0"],
        verdict="AC",
    )
    # 查询推荐
    template, _app, _chal, _nr, _prof = await recommend_for_slots(db_session, user_id, kp_chain["C"])
    template_ids = {p.id for p in template}
    assert problems_with_rating["p0"] not in template_ids
