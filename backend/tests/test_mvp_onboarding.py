"""用户档案、CF 绑定、冷启动和错题闭环的 MVP 回归测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.deps import get_codeforces_api_client
from app.main import app
from app.models.codeforces import CodeforcesAccount
from app.models.knowledge import KnowledgePoint
from app.models.learning import LearningPath, UserProblemAC
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.models.wrongbook import WrongBookEntry
from app.services.codeforces.sync import sync_user_status
from app.services.onboarding import select_diagnostic_problems


class FakeCodeforcesClient:
    def __init__(self) -> None:
        self.submissions: list[dict] = []

    async def user_info(self, handle: str) -> list[dict]:
        if handle == "missing":
            return []
        return [{"handle": "Tourist", "rating": 3850}]

    async def user_status(self, handle: str, *, from_: int | None = None, count: int | None = None) -> list[dict]:
        return self.submissions

    async def user_rating(self, handle: str) -> list[dict]:
        return []


@pytest.fixture
def fake_cf() -> FakeCodeforcesClient:
    fake = FakeCodeforcesClient()

    async def override():
        yield fake

    app.dependency_overrides[get_codeforces_api_client] = override
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_codeforces_api_client, None)


@pytest.mark.asyncio
async def test_profile_update_and_cf_binding(client, auth_user, fake_cf, db_session):
    profile_response = await client.patch(
        "/api/v1/auth/profile",
        json={
            "username": "acm_student",
            "school": "Example University",
            "atcoder_handle": "atcoder_user",
            "target_medal": "gold",
        },
        headers=auth_user["headers"],
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["school"] == "Example University"

    bind_response = await client.post(
        "/api/v1/auth/codeforces/bind",
        json={"handle": "tourist"},
        headers=auth_user["headers"],
    )
    assert bind_response.status_code == 200
    body = bind_response.json()
    assert body["account"]["handle"] == "Tourist"
    assert body["account"]["current_rating"] == 3850
    assert body["user"]["cf_handle"] == "Tourist"

    account = (
        await db_session.execute(
            select(CodeforcesAccount).where(CodeforcesAccount.user_id == auth_user["user"].id)
        )
    ).scalar_one()
    assert account.handle == "Tourist"


@pytest.mark.asyncio
async def test_minimal_diagnostic_cold_start(client, auth_user, fake_cf, seed_data, db_session):
    start_response = await client.post("/api/v1/onboarding/start", headers=auth_user["headers"])
    assert start_response.status_code == 200
    start = start_response.json()
    assert start["mode"] == "diagnostic_required"
    assert start["completed"] is False
    assert [item["id"] for item in start["diagnostic_problems"]] == [str(seed_data["problem_id"])]

    submit_response = await client.post(
        "/api/v1/onboarding/diagnostic",
        json={"results": [{"problem_id": str(seed_data["problem_id"]), "correct": True}]},
        headers=auth_user["headers"],
    )
    assert submit_response.status_code == 200
    result = submit_response.json()
    assert result["completed"] is True
    assert result["mode"] == "diagnostic"
    assert result["learning_path_id"] is not None

    ac = (
        await db_session.execute(
            select(UserProblemAC).where(
                UserProblemAC.user_id == auth_user["user"].id,
                UserProblemAC.problem_id == seed_data["problem_id"],
            )
        )
    ).scalar_one()
    path = (
        await db_session.execute(
            select(LearningPath).where(
                LearningPath.user_id == auth_user["user"].id,
                LearningPath.is_active.is_(True),
            )
        )
    ).scalar_one()
    assert ac is not None
    assert path is not None


@pytest.mark.asyncio
async def test_diagnostic_selector_reaches_fifteen_problems_and_ten_knowledge_points(
    db_session,
    seed_data,
):
    suffix = uuid4().hex[:8]
    knowledge_points = [
        KnowledgePoint(
            name=f"诊断知识点 {index}-{suffix}",
            slug=f"diagnostic-kp-{index}-{suffix}",
            order=index,
        )
        for index in range(9)
    ]
    db_session.add_all(knowledge_points)
    await db_session.flush()

    difficulties = (
        [ProblemDifficulty.EASY] * 4
        + [ProblemDifficulty.MEDIUM] * 7
        + [ProblemDifficulty.HARD] * 3
    )
    for index, difficulty in enumerate(difficulties):
        problem = Problem(
            title=f"诊断题 {index}-{suffix}",
            slug=f"diagnostic-problem-{index}-{suffix}",
            description="覆盖诊断题选择器",
            difficulty=difficulty,
            status=ProblemStatus.PUBLISHED,
            submit_count=index,
        )
        problem.knowledge_points = [knowledge_points[index % len(knowledge_points)]]
        db_session.add(problem)
    await db_session.flush()

    selected = await select_diagnostic_problems(db_session)

    assert len(selected) == 15
    assert len({knowledge_id for problem in selected for knowledge_id in problem.knowledge_point_ids}) >= 10
    assert sum(problem.difficulty == "easy" for problem in selected) == 5
    assert sum(problem.difficulty == "medium" for problem in selected) == 7
    assert sum(problem.difficulty == "hard" for problem in selected) == 3


@pytest.mark.asyncio
async def test_cf_sync_creates_and_resolves_wrongbook_entry(
    client,
    auth_user,
    fake_cf,
    seed_data,
    db_session,
):
    problem = (
        await db_session.execute(select(Problem).where(Problem.id == seed_data["problem_id"]))
    ).scalar_one()
    problem.cf_contest_id = 100
    problem.cf_index = "A"
    account = CodeforcesAccount(user_id=auth_user["user"].id, handle="Tourist", current_rating=3850)
    db_session.add(account)
    await db_session.flush()

    fake_cf.submissions = [
        {
            "id": 1001,
            "problem": {"contestId": 100, "index": "A"},
            "verdict": "WRONG_ANSWER",
            "programmingLanguage": "GNU C++20",
            "creationTimeSeconds": int(datetime.now(UTC).timestamp()),
            "timeConsumedMillis": 31,
            "memoryConsumedBytes": 1024,
            "passedTestCount": 2,
        }
    ]
    first = await sync_user_status(db_session, account, fake_cf)
    assert first["new_submissions"] == 1
    wrong = (
        await db_session.execute(
            select(WrongBookEntry).where(WrongBookEntry.user_id == auth_user["user"].id)
        )
    ).scalar_one()
    assert wrong.resolved is False

    list_response = await client.get("/api/v1/wrongbook", headers=auth_user["headers"])
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    fake_cf.submissions = [
        {
            "id": 1002,
            "problem": {"contestId": 100, "index": "A"},
            "verdict": "OK",
            "programmingLanguage": "GNU C++20",
            "creationTimeSeconds": int(datetime.now(UTC).timestamp()),
            "timeConsumedMillis": 15,
            "memoryConsumedBytes": 1024,
            "passedTestCount": 10,
        }
    ]
    second = await sync_user_status(db_session, account, fake_cf)
    assert second["new_ac"] == 1
    await db_session.refresh(wrong)
    assert wrong.resolved is True
