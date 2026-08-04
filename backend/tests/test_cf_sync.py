"""Codeforces 同步服务测试 (Task 8.2 / 8.3 / 8.4)。

覆盖：
- problemset 同步的新增、更新和重复执行幂等
- user.status 增量同步
- 同一秒多条提交不会漏同步
- Submission 不保存源代码
- OK submission 正确生成 UserProblemAC
- 重复同步不会重复生成 AC、Submission 或 RatingHistory
- 单个账号失败不影响其他账号
- Rating 空历史处理
- streak_days 和 rating_history 正确进入进度面板
- 真正的分页同步：多页数据不丢失
- Celery 任务连续两轮执行不因跨事件循环 Redis 复用崩溃
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.learning import UserProblemAC
from app.models.problem import Problem, ProblemSource, ProblemStatus
from app.services.codeforces.sync import (
    sync_all_users_status,
    sync_problemset,
    sync_user_rating,
    sync_user_status,
)


def _make_cf_problem(
    contest_id: int = 100,
    index: str = "A",
    name: str = "Test Problem",
    rating: int | None = 1200,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """构造 CF problemset.problems 单条题目。"""
    return {
        "contestId": contest_id,
        "index": index,
        "name": name,
        "rating": rating,
        "tags": tags or ["dp", "greedy"],
    }


def _make_cf_submission(
    sub_id: int,
    contest_id: int = 100,
    index: str = "A",
    verdict: str = "OK",
    lang: str = "Python 3",
    ts: int | None = None,
    passed_test_count: int = 10,
) -> dict[str, Any]:
    """构造 CF user.status 单条提交。"""
    if ts is None:
        ts = int(datetime.now(tz=UTC).timestamp())
    return {
        "id": sub_id,
        "creationTimeSeconds": ts,
        "verdict": verdict,
        "programmingLanguage": lang,
        "timeConsumedMillis": 100,
        "memoryConsumedBytes": 1024,
        "passedTestCount": passed_test_count,
        "problem": {
            "contestId": contest_id,
            "index": index,
            "name": "Test Problem",
            "tags": ["dp"],
        },
    }


def _make_cf_rating_change(
    contest_id: int = 200,
    new_rating: int = 1500,
    old_rating: int = 1400,
    ts: int | None = None,
) -> dict[str, Any]:
    """构造 CF user.rating 单条 rating 变更。"""
    if ts is None:
        ts = int(datetime.now(tz=UTC).timestamp())
    return {
        "contestId": contest_id,
        "contestName": f"Test Contest {contest_id}",
        "rank": 100,
        "oldRating": old_rating,
        "newRating": new_rating,
        "ratingUpdateTimeSeconds": ts,
    }


class FakeCodeforcesClient:
    """测试用 fake CF API 客户端。

    user_status 支持真正的分页：按 from_+count 从全量数据切片返回，
    模拟 CF API 行为（按 submission id 降序）。
    """

    def __init__(
        self,
        problemset: dict | None = None,
        user_status: list | None = None,
        user_rating: list | None = None,
    ) -> None:
        self._problemset = problemset or {"problems": [], "problemStatistics": []}
        # user_status 内部按 submission id 降序保存（最新在前）
        self._user_status = sorted(
            user_status or [],
            key=lambda s: s["id"],
            reverse=True,
        )
        self._user_rating = user_rating or []

    async def problemset_problems(self, tags: list[str] | None = None) -> dict[str, Any]:
        return self._problemset

    async def user_status(
        self,
        handle: str,
        *,
        from_: int | None = None,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """模拟 CF API 分页：from_ 是 1-based 起始索引。"""
        start = (from_ or 1) - 1
        end = start + count if count is not None else None
        return self._user_status[start:end]

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        return self._user_rating

    async def user_info(self, handle: str) -> list[dict[str, Any]]:
        return [{"handle": handle}]


# ===== 1. problemset 同步：新增、更新、幂等 =====


@pytest.mark.asyncio
async def test_problemset_sync_creates_new_problems(db_session: AsyncSession):
    """problemset 同步新增 CF 题目。

    使用 900001/900002 这种不会被真实 CF 使用的 contest_id，避免与开发库已有数据冲突。
    只断言本次新增的 slug 存在（不依赖全表 count，避免数据污染）。
    """
    client = FakeCodeforcesClient(
        problemset={
            "problems": [
                _make_cf_problem(900001, "A", "Problem A", 1200),
                _make_cf_problem(900002, "B", "Problem B", 1400),
            ]
        }
    )
    result = await sync_problemset(db_session, client)

    assert result["synced"] == 2
    assert result["total"] == 2
    # 验证 DB 写入：只查本次同步的两道题
    probs = (
        (
            await db_session.execute(
                select(Problem).where(
                    Problem.source == ProblemSource.CODEFORCES,
                    Problem.cf_contest_id.in_([900001, 900002]),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(probs) == 2
    assert all(p.status == ProblemStatus.PUBLISHED for p in probs)
    assert all(p.external_url is not None for p in probs)
    # slug 应为 cf-{contest_id}-{index}
    slugs = {p.slug for p in probs}
    assert "cf-900001-A" in slugs
    assert "cf-900002-B" in slugs


@pytest.mark.asyncio
async def test_problemset_sync_updates_existing(db_session: AsyncSession):
    """重复同步更新题目名称、tags、rating。"""
    # 第一次同步
    client1 = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Old Name", 1000)]})
    await sync_problemset(db_session, client1)

    # 第二次同步，名字和 rating 改变
    client2 = FakeCodeforcesClient(
        problemset={"problems": [_make_cf_problem(900001, "A", "New Name", 1500, ["dp", "math"])]}
    )
    await sync_problemset(db_session, client2)

    probs = (
        (
            await db_session.execute(
                select(Problem).where(
                    Problem.cf_contest_id == 900001,
                    Problem.cf_index == "A",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(probs) == 1
    assert probs[0].title == "New Name"
    assert probs[0].cf_rating == 1500.0
    assert probs[0].cf_tags == ["dp", "math"]


@pytest.mark.asyncio
async def test_problemset_sync_idempotent(db_session: AsyncSession):
    """重复同步同一批题目不产生重复记录。"""
    client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900003, "A", "Test", 1200)]})
    await sync_problemset(db_session, client)
    await sync_problemset(db_session, client)
    await sync_problemset(db_session, client)

    count = (
        (
            await db_session.execute(
                select(Problem).where(
                    Problem.cf_contest_id == 900003,
                    Problem.cf_index == "A",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(count) == 1


@pytest.mark.asyncio
async def test_problemset_sync_does_not_delete_platform_problems(db_session: AsyncSession):
    """同步不删除平台自建题目。"""
    # 先建一个 platform 题
    platform_p = Problem(
        id=uuid4(),
        title="Platform Problem",
        slug=f"platform-{uuid4().hex[:8]}",
        description="test",
        source=ProblemSource.PLATFORM,
        status=ProblemStatus.PUBLISHED,
    )
    db_session.add(platform_p)
    await db_session.flush()

    # 同步 CF 题目
    client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900004, "A", "CF Problem", 1200)]})
    await sync_problemset(db_session, client)

    # platform 题应该还在
    found = (await db_session.execute(select(Problem).where(Problem.id == platform_p.id))).scalar_one_or_none()
    assert found is not None
    assert found.source == ProblemSource.PLATFORM


# ===== 2. user.status 增量同步 =====


@pytest.mark.asyncio
async def test_user_status_sync_creates_submissions(db_session: AsyncSession):
    """user.status 同步创建 Submission 记录。"""
    user_id = uuid4()
    account = CodeforcesAccount(
        id=uuid4(),
        user_id=user_id,
        handle="testuser",
    )
    db_session.add(account)

    # 先同步 CF 题目
    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    # 同步 user.status
    ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(
        user_status=[
            _make_cf_submission(1001, 900001, "A", "OK", ts=ts),
            _make_cf_submission(1002, 900001, "A", "WRONG_ANSWER", ts=ts + 1),
        ]
    )
    result = await sync_user_status(db_session, account, client)

    assert result["new_submissions"] == 2
    assert result["new_ac"] == 1
    # 游标更新
    assert account.last_submission_id == 1002

    # 验证 Submission 记录
    subs = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(subs) == 2
    # 关联 problem_id
    assert all(s.problem_id is not None for s in subs)


@pytest.mark.asyncio
async def test_user_status_sync_same_second_no_miss(db_session: AsyncSession):
    """同一秒多条提交不会漏同步。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    # 先同步 CF 题目
    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    # 同一秒（同一 creationTimeSeconds）的多条提交
    same_ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(
        user_status=[
            _make_cf_submission(1001, 900001, "A", "OK", ts=same_ts),
            _make_cf_submission(1002, 900001, "A", "OK", ts=same_ts),
            _make_cf_submission(1003, 900001, "A", "WRONG_ANSWER", ts=same_ts),
        ]
    )
    result = await sync_user_status(db_session, account, client)

    assert result["new_submissions"] == 3
    subs = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(subs) == 3
    # 游标是最大 submission id
    assert account.last_submission_id == 1003


@pytest.mark.asyncio
async def test_user_status_sync_incremental(db_session: AsyncSession):
    """增量同步：第二次只拉取比游标更新的提交。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    ts = int(datetime.now(tz=UTC).timestamp())
    # 第一次同步
    client1 = FakeCodeforcesClient(
        user_status=[
            _make_cf_submission(1001, 900001, "A", "OK", ts=ts),
            _make_cf_submission(1002, 900001, "A", "WRONG_ANSWER", ts=ts + 1),
        ]
    )
    await sync_user_status(db_session, account, client1)
    assert account.last_submission_id == 1002

    # 第二次：API 仍返回全部（最新 1000 条），但只有游标后的算新增
    # 1003 是另一道题的 AC（避免与 1001 同题 AC，否则幂等去重 new_ac=0）
    client2 = FakeCodeforcesClient(
        user_status=[
            _make_cf_submission(1001, 900001, "A", "OK", ts=ts),
            _make_cf_submission(1002, 900001, "A", "WRONG_ANSWER", ts=ts + 1),
            _make_cf_submission(1003, 900001, "B", "OK", ts=ts + 2),  # 新题 B 的 AC
        ]
    )
    # 同步 CF 题目 B（使 problem_id 能关联）
    cf_client_problemset2 = FakeCodeforcesClient(
        problemset={
            "problems": [
                _make_cf_problem(900001, "A", "Test A", 1200),
                _make_cf_problem(900001, "B", "Test B", 1300),
            ]
        }
    )
    await sync_problemset(db_session, cf_client_problemset2)

    result = await sync_user_status(db_session, account, client2)

    # 只有 1003 是新的 submission；它是新题 B 的 AC，所以 new_ac=1
    assert result["new_submissions"] == 1
    assert result["new_ac"] == 1
    assert account.last_submission_id == 1003


@pytest.mark.asyncio
async def test_submission_does_not_store_source_code(db_session: AsyncSession):
    """Submission 表不保存源代码字段。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(user_status=[_make_cf_submission(1001, 900001, "A", "OK", ts=ts)])
    await sync_user_status(db_session, account, client)

    sub = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalar_one()
    # Submission 模型不应有 source_code 字段
    assert not hasattr(sub, "source_code")
    assert not hasattr(sub, "code")


@pytest.mark.asyncio
async def test_ok_submission_creates_user_problem_ac(db_session: AsyncSession):
    """verdict=OK 的 submission 写入 UserProblemAC。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(user_status=[_make_cf_submission(1001, 900001, "A", "OK", ts=ts)])
    await sync_user_status(db_session, account, client)

    ac = (await db_session.execute(select(UserProblemAC).where(UserProblemAC.user_id == user_id))).scalar_one_or_none()
    assert ac is not None


@pytest.mark.asyncio
async def test_repeated_sync_does_not_duplicate_ac(db_session: AsyncSession):
    """重复同步不会重复生成 AC。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    cf_client_problemset = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client_problemset)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(user_status=[_make_cf_submission(1001, 900001, "A", "OK", ts=ts)])

    # 第一次同步
    await sync_user_status(db_session, account, client)
    # 重置游标模拟重复
    account.last_submission_id = 0
    # 第二次同步（API 返回同样的数据）
    await sync_user_status(db_session, account, client)

    ac_count = (await db_session.execute(select(UserProblemAC).where(UserProblemAC.user_id == user_id))).scalars().all()
    assert len(ac_count) == 1

    sub_count = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(sub_count) == 1


# ===== 3. user.rating 同步 =====


@pytest.mark.asyncio
async def test_user_rating_sync_creates_history(db_session: AsyncSession):
    """user.rating 同步创建 RatingHistory。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    ts1 = int(datetime.now(tz=UTC).timestamp())
    ts2 = ts1 + 86400  # 一天后
    client = FakeCodeforcesClient(
        user_rating=[
            _make_cf_rating_change(200, 1500, 1400, ts1),
            _make_cf_rating_change(201, 1600, 1500, ts2),
        ]
    )
    result = await sync_user_rating(db_session, account, client)

    assert result["new_ratings"] == 2
    assert result["current_rating"] == 1600
    assert account.current_rating == 1600

    history = (await db_session.execute(select(RatingHistory).where(RatingHistory.user_id == user_id))).scalars().all()
    assert len(history) == 2


@pytest.mark.asyncio
async def test_user_rating_sync_idempotent(db_session: AsyncSession):
    """重复同步 RatingHistory 不产生重复。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FakeCodeforcesClient(user_rating=[_make_cf_rating_change(200, 1500, 1400, ts)])

    await sync_user_rating(db_session, account, client)
    result2 = await sync_user_rating(db_session, account, client)

    assert result2["new_ratings"] == 0
    history = (await db_session.execute(select(RatingHistory).where(RatingHistory.user_id == user_id))).scalars().all()
    assert len(history) == 1


@pytest.mark.asyncio
async def test_user_rating_empty_history(db_session: AsyncSession):
    """从未参加 rated contest 的用户同步空历史不报错。"""
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser", current_rating=None)
    db_session.add(account)

    client = FakeCodeforcesClient(user_rating=[])
    result = await sync_user_rating(db_session, account, client)

    assert result["new_ratings"] == 0
    assert result["current_rating"] is None
    assert account.current_rating is None


# ===== 4. 分页拉取策略 =====


class PagingSpyCodeforcesClient:
    """记录 user_status 调用参数并模拟真正分页的 fake client。

    按 from_+count 从全量数据切片返回（降序），用于验证：
    - 首次同步会循环拉取多页直到拉完
    - 增量同步遇到游标即停止
    - 多页数据不会丢失
    """

    def __init__(self, user_status: list, rating_data: list | None = None) -> None:
        # 内部按 submission id 降序保存
        self._user_status = sorted(user_status, key=lambda s: s["id"], reverse=True)
        self._user_rating = rating_data or []
        self.captured_calls: list[tuple[int | None, int | None]] = []

    async def problemset_problems(self, tags=None):  # type: ignore[no-untyped-def]
        return {"problems": [], "problemStatistics": []}

    async def user_status(
        self,
        handle: str,
        *,
        from_: int | None = None,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        self.captured_calls.append((from_, count))
        start = (from_ or 1) - 1
        end = start + count if count is not None else None
        return self._user_status[start:end]

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        return self._user_rating

    async def user_info(self, handle: str) -> list[dict[str, Any]]:
        return [{"handle": handle}]


@pytest.mark.asyncio
async def test_user_status_initial_sync_paginates_until_exhausted(db_session: AsyncSession):
    """首次同步多页拉取，所有 submission 都写入，不丢数据。

    准备 2500 条 submission（需要 3 页：1000 + 1000 + 500）。
    """
    user_id = uuid4()
    account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle="testuser")
    db_session.add(account)

    # 同步 CF 题目供 problem_id 关联
    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    # 2500 条 submission，id 从 1 到 2500
    ts = int(datetime.now(tz=UTC).timestamp())
    all_subs = [
        _make_cf_submission(i, 900001, "A", "OK" if i % 2 == 0 else "WRONG_ANSWER", ts=ts) for i in range(1, 2501)
    ]

    client = PagingSpyCodeforcesClient(user_status=all_subs)
    result = await sync_user_status(db_session, account, client)

    # 所有 2500 条都应写入
    assert result["new_submissions"] == 2500
    assert account.last_submission_id == 2500
    # 应该拉取了 3 页（1000 + 1000 + 500）
    assert result["pages_fetched"] == 3, f"expected 3 pages, got {result['pages_fetched']}"
    # 验证调用参数：from_=1,1001,2001
    froms = [call[0] for call in client.captured_calls]
    assert froms == [1, 1001, 2001], f"unexpected from_ values: {froms}"

    # DB 中确实有 2500 条
    subs = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(subs) == 2500


@pytest.mark.asyncio
async def test_user_status_incremental_sync_stops_at_cursor(db_session: AsyncSession):
    """增量同步遇到游标之前的 submission 立即停止，不拉冗余页。"""
    user_id = uuid4()
    account = CodeforcesAccount(
        id=uuid4(),
        user_id=user_id,
        handle="testuser",
        last_submission_id=1000,  # 游标
    )
    db_session.add(account)

    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    ts = int(datetime.now(tz=UTC).timestamp())
    # API 返回 1500 条（id 1-1500），其中 1001-1500 是新的
    all_subs = [_make_cf_submission(i, 900001, "A", "OK", ts=ts) for i in range(1, 1501)]
    client = PagingSpyCodeforcesClient(user_status=all_subs)
    result = await sync_user_status(db_session, account, client)

    # 只有 1001-1500 是新的（500 条）
    assert result["new_submissions"] == 500
    assert account.last_submission_id == 1500
    # 第一页就包含游标之前的 submission（id<=1000），应停止
    # 第一页返回 1000 条（id 501-1500，因为降序），其中 id 1001-1500 是新的，id 501-1000 是旧的
    # len(new_in_page)=500 < len(page)=1000 → reached_cursor=True → 停止
    assert result["pages_fetched"] == 1, f"expected 1 page, got {result['pages_fetched']}"


@pytest.mark.asyncio
async def test_user_status_incremental_sync_no_new_submissions(db_session: AsyncSession):
    """增量同步时第一页全部 <= 游标，立即停止，不拉第二页。"""
    user_id = uuid4()
    account = CodeforcesAccount(
        id=uuid4(),
        user_id=user_id,
        handle="testuser",
        last_submission_id=2000,  # 游标比所有 API 返回的都大
    )
    db_session.add(account)

    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    ts = int(datetime.now(tz=UTC).timestamp())
    all_subs = [_make_cf_submission(i, 900001, "A", "OK", ts=ts) for i in range(1, 1001)]
    client = PagingSpyCodeforcesClient(user_status=all_subs)
    result = await sync_user_status(db_session, account, client)

    assert result["new_submissions"] == 0
    # 第一页全部 <= 游标，应立即停止
    assert result["pages_fetched"] == 1
    assert len(client.captured_calls) == 1, "should not fetch second page when first page all <= cursor"


@pytest.mark.asyncio
async def test_user_status_incremental_truncated_does_not_advance_cursor(
    db_session: AsyncSession,
    monkeypatch,
):
    """增量同步超过 max_pages 上限时游标不推进，防止数据丢失。

    回归 P1：旧实现在 reached_cursor=False 时仍推进游标到 max_sub_id，
    导致 10000 条之后的更老新提交被永久标记为"已同步"而丢失。

    本测试模拟用户在 5 分钟间隔内提交了 12000 条（超过 10 页 × 1000），
    验证：
    1. 游标保持不变（truncated=True 时不推进）
    2. 返回值 truncated=True
    3. 已拉取的 10000 条仍然写入 DB（幂等约束保证下次不重复）
    4. 下次同步（API 仍返回同样数据）能补上剩余 2000 条
    """
    # 临时把 max_pages 调小到 3，模拟 truncated（3 页 × 1000 = 3000 条，但 API 有 5000 条）
    import app.services.codeforces.sync as sync_module

    original_max_pages = sync_module.USER_STATUS_INCREMENTAL_MAX_PAGES
    monkeypatch.setattr(sync_module, "USER_STATUS_INCREMENTAL_MAX_PAGES", 3)

    user_id = uuid4()
    account = CodeforcesAccount(
        id=uuid4(),
        user_id=user_id,
        handle="testuser",
        last_submission_id=1000,  # 游标
    )
    db_session.add(account)

    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    ts = int(datetime.now(tz=UTC).timestamp())
    # API 返回 5000 条（id 1001-6000），全部 > 游标 1000
    all_subs = [_make_cf_submission(i, 900001, "A", "OK", ts=ts) for i in range(1001, 6001)]
    client = PagingSpyCodeforcesClient(user_status=all_subs)
    result = await sync_user_status(db_session, account, client)

    # 拉了 3 页（3000 条），但未到达游标（所有返回的都 > 1000）
    assert result["pages_fetched"] == 3
    assert result["truncated"] is True
    assert result["reached_cursor"] is False
    assert result["new_submissions"] == 3000
    # 关键：游标未推进！仍是 1000
    assert account.last_submission_id == 1000, (
        f"cursor must NOT advance when truncated, got {account.last_submission_id}"
    )

    # 已拉取的 3000 条确实写入 DB
    subs = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(subs) == 3000

    # 第二轮同步：API 仍返回同样数据，应补齐剩余 2000 条（幂等跳过已写入的 3000 条）
    # 因游标未推进，仍按 last_id=1000 过滤，但 max_pages=3 只能拉 3000 条
    # 已写入的 3000 条会被 ON CONFLICT DO NOTHING 跳过，new_submissions=0
    client2 = PagingSpyCodeforcesClient(user_status=all_subs)
    result2 = await sync_user_status(db_session, account, client2)
    assert result2["new_submissions"] == 0  # 全部幂等跳过
    assert result2["truncated"] is True
    assert account.last_submission_id == 1000  # 游标仍未推进

    # 恢复 max_pages 后一次性拉完
    monkeypatch.setattr(sync_module, "USER_STATUS_INCREMENTAL_MAX_PAGES", original_max_pages)
    client3 = PagingSpyCodeforcesClient(user_status=all_subs)
    result3 = await sync_user_status(db_session, account, client3)
    # 第三轮 max_pages=10，拉完 5 页后第 6 页空 → reached_cursor=True → 推进游标
    # 前两轮 truncated 只拉了 3000 条（id 1001-4000），第三轮补齐 id 4001-6000 共 2000 条
    assert result3["reached_cursor"] is True
    assert result3["truncated"] is False
    assert result3["new_submissions"] == 2000  # 补齐之前未拉到的 2000 条
    # 游标推进到最大 id（6000）
    assert account.last_submission_id == 6000
    # 总共 5000 条都在 DB
    all_subs_in_db = (await db_session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
    assert len(all_subs_in_db) == 5000


# ===== 5. 单用户失败隔离 =====


class FailingThenSucceedingClient:
    """第一个账号调用失败，第二个账号调用成功的 fake client。

    用于验证 sync_all_users_status 的单账号失败隔离。
    """

    def __init__(self, fail_handle: str, user_status_data: list) -> None:
        self._fail_handle = fail_handle
        self._user_status = sorted(user_status_data, key=lambda s: s["id"], reverse=True)
        self._problemset = {"problems": [], "problemStatistics": []}

    async def problemset_problems(self, tags=None):  # type: ignore[no-untyped-def]
        return self._problemset

    async def user_status(
        self,
        handle: str,
        *,
        from_: int | None = None,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        if handle == self._fail_handle:
            raise RuntimeError("simulated CF API failure")
        start = (from_ or 1) - 1
        end = start + count if count is not None else None
        return self._user_status[start:end]

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        return []

    async def user_info(self, handle: str) -> list[dict[str, Any]]:
        return [{"handle": handle}]


@pytest.mark.asyncio
async def test_sync_all_users_status_single_failure_isolated(db_session: AsyncSession):
    """单个账号同步失败不影响其他账号，失败状态正确传播。"""
    # 两个账号：user1 会失败，user2 会成功
    user1_id = uuid4()
    user2_id = uuid4()
    account1 = CodeforcesAccount(id=uuid4(), user_id=user1_id, handle="fail_user")
    account2 = CodeforcesAccount(id=uuid4(), user_id=user2_id, handle="ok_user")
    db_session.add_all([account1, account2])

    # 先同步 CF 题目供 user2 关联
    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FailingThenSucceedingClient(
        fail_handle="fail_user",
        user_status_data=[_make_cf_submission(2001, 900001, "A", "OK", ts=ts)],
    )
    results = await sync_all_users_status(db_session, client)

    assert len(results) == 2
    # 找到失败和成功的账号
    by_handle = {r["handle"]: r for r in results}
    assert by_handle["fail_user"]["status"] == "error"
    assert "error" in by_handle["fail_user"]
    assert by_handle["ok_user"]["status"] == "ok"
    assert by_handle["ok_user"]["new_submissions"] == 1
    assert by_handle["ok_user"]["new_ac"] == 1

    # user2 的 submission 应该正常写入
    from sqlalchemy import select as _select

    subs = (await db_session.execute(_select(Submission).where(Submission.user_id == user2_id))).scalars().all()
    assert len(subs) == 1


@pytest.mark.asyncio
async def test_sync_all_users_status_failure_propagates_to_celery_task(db_session: AsyncSession):
    """sync_all_users_status 返回的 status 字段正确反映失败情况。"""
    # 一个账号失败，一个账号成功 → 整体 status="partial"
    user1_id = uuid4()
    user2_id = uuid4()
    account1 = CodeforcesAccount(id=uuid4(), user_id=user1_id, handle="fail_user")
    account2 = CodeforcesAccount(id=uuid4(), user_id=user2_id, handle="ok_user")
    db_session.add_all([account1, account2])

    cf_client = FakeCodeforcesClient(problemset={"problems": [_make_cf_problem(900001, "A", "Test", 1200)]})
    await sync_problemset(db_session, cf_client)

    ts = int(datetime.now(tz=UTC).timestamp())
    client = FailingThenSucceedingClient(
        fail_handle="fail_user",
        user_status_data=[_make_cf_submission(2001, 900001, "A", "OK", ts=ts)],
    )
    results = await sync_all_users_status(db_session, client)

    # 验证 status 字段存在且正确
    statuses = {r["status"] for r in results}
    assert "error" in statuses
    assert "ok" in statuses


# ===== 6. Celery 跨事件循环回归测试 =====


def test_get_codeforces_client_does_not_cache_across_calls():
    """get_codeforces_client 每次返回新实例，不缓存跨事件循环的 Redis 连接。

    回归 P1-1：旧实现把 _client 缓存在模块级单例中，第一个 Celery 任务创建的
    Redis 连接绑定到旧事件循环，第二个任务复用时会抛
    "Future attached to a different loop" / "Event loop is closed"。
    """
    from app.services.codeforces.client import get_codeforces_client

    # 传 use_redis=False 避免真实 Redis 连接（本测试只验证不缓存）
    c1 = get_codeforces_client(use_redis=False)
    c2 = get_codeforces_client(use_redis=False)
    assert c1 is not c2, "get_codeforces_client must not cache client across calls"


@pytest.mark.slow
def test_celery_task_two_consecutive_runs_no_cross_loop_error(monkeypatch):
    """同一 Celery 进程连续执行两轮 CF 任务，不因跨事件循环 Redis 复用崩溃。

    回归 P1-1：旧实现用模块级 _client 单例缓存 Redis 连接，第一轮任务在
    asyncio.run() 创建的 loop A 中创建 Redis 连接，loop A 关闭后第二轮任务
    在新的 loop B 中复用同一 Redis 连接，抛
    "RuntimeError: Future attached to a different loop" /
    "RuntimeError: Event loop is closed"。

    本测试用真实 Redis（验证跨事件循环修复）+ 模拟 CF API（不依赖网络）。
    需要 docker compose 环境（Redis + PostgreSQL 可达）。
    """
    from app.tasks import cf_tasks as cf_tasks_module

    # 准备 mock CF 题目（contest_id 900001 避免与真实 CF 数据冲突）
    fake_problemset = {
        "problems": [
            {
                "contestId": 900001,
                "index": "A",
                "name": "Mock Problem A",
                "rating": 1200,
                "tags": ["dp"],
            }
        ],
        "problemStatistics": [],
    }

    class MockCFClient:
        """不含 Redis 的 fake CF client，避免真实 CF API 调用。

        跨事件循环的验证由真实的 Redis 完成（_run_with_session 内
        get_codeforces_client() 仍创建真实 Redis 连接，但 CF API 用 mock）。
        """

        def __init__(self):
            pass

        async def problemset_problems(self, tags=None):  # type: ignore[no-untyped-def]
            return fake_problemset

        async def user_status(self, handle, *, from_=None, count=None):  # type: ignore[no-untyped-def]
            return []

        async def user_rating(self, handle):  # type: ignore[no-untyped-def]
            return []

        async def user_info(self, handle):  # type: ignore[no-untyped-def]
            return [{"handle": handle}]

    # 注入 fake client 工厂（_run_with_session 会优先使用）
    monkeypatch.setattr(cf_tasks_module, "_test_client_factory", lambda: MockCFClient())

    from app.tasks.cf_tasks import sync_problemset_task

    # 第一轮：应成功（在 loop A 中创建并关闭 Redis 连接）
    result1 = sync_problemset_task.apply()
    assert result1.successful(), f"first run failed: {result1.result}"
    assert "synced" in result1.result

    # 第二轮：应也成功，不应因跨事件循环 Redis 复用崩溃
    result2 = sync_problemset_task.apply()
    assert result2.successful(), f"second run failed (cross-event-loop regression): {result2.result}"
    assert "synced" in result2.result
