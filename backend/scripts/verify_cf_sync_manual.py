"""手动触发 CF 同步验证脚本（受控数据，不依赖真实 CF 网络）。

使用方法：
    docker compose exec backend python -m scripts.verify_cf_sync_manual

验证内容：
1. problemset 同步写入 CF 题目
2. user.status 同步写入 Submission + OK 写入 UserProblemAC
3. user.rating 同步写入 RatingHistory + 更新 current_rating
4. 重复同步幂等（不产生重复记录）
5. GET /api/v1/progress/overview 返回的 streak_days / rating_history 正确接入

完成验证后报告 PASS / FAIL。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.learning import UserProblemAC
from app.models.problem import Problem, ProblemSource
from app.schemas.progress import ProgressOverviewResponse
from app.services.codeforces.sync import (
    sync_problemset,
    sync_user_rating,
    sync_user_status,
)
from app.services.progress import get_progress_overview

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class FakeCFClient:
    """受控数据 fake CF client。

    注意：实例属性使用 _ 前缀，避免与方法同名（否则方法会被属性遮蔽）。
    """

    def __init__(self) -> None:
        # 使用 900001/900002 这种不会被真实 CF 使用的 contest_id
        # 与 cleanup_cf_test_data.py 的 MOCK_CF_CONTEST_IDS 保持一致
        self._problemset = {
            "problems": [
                {
                    "contestId": 900001,
                    "index": "A",
                    "name": "Mock Problem A",
                    "rating": 1200,
                    "tags": ["dp", "greedy"],
                },
                {
                    "contestId": 900002,
                    "index": "B",
                    "name": "Mock Problem B",
                    "rating": 1400,
                    "tags": ["math"],
                },
            ],
            "problemStatistics": [],
        }
        # 两条提交：一条 OK，一条 WRONG_ANSWER，时间差 1 秒
        now_ts = int(datetime.now(tz=UTC).timestamp())
        self._user_status = [
            {
                "id": 9001,
                "creationTimeSeconds": now_ts,
                "verdict": "OK",
                "programmingLanguage": "Python 3",
                "timeConsumedMillis": 100,
                "memoryConsumedBytes": 1024,
                "passedTestCount": 10,
                "problem": {
                    "contestId": 900001,
                    "index": "A",
                    "name": "Mock Problem A",
                    "tags": ["dp"],
                },
            },
            {
                "id": 9002,
                "creationTimeSeconds": now_ts + 1,
                "verdict": "WRONG_ANSWER",
                "programmingLanguage": "Python 3",
                "timeConsumedMillis": 50,
                "memoryConsumedBytes": 512,
                "passedTestCount": 3,
                "problem": {
                    "contestId": 900002,
                    "index": "B",
                    "name": "Mock Problem B",
                    "tags": ["math"],
                },
            },
        ]
        # rating 历史：一次参赛，rating 从 1400 -> 1500
        # contest_id 用 900003 避免与真实 CF 冲突
        self._user_rating = [
            {
                "contestId": 900003,
                "contestName": "Mock Rated Round",
                "rank": 100,
                "oldRating": 1400,
                "newRating": 1500,
                "ratingUpdateTimeSeconds": now_ts - 86400,
            }
        ]

    async def problemset_problems(self, tags=None):  # type: ignore[no-untyped-def]
        return self._problemset

    async def user_status(self, handle, *, from_=None, count=None):  # type: ignore[no-untyped-def]
        """模拟 CF API 分页：from_+count 切片，按 submission id 降序。"""
        start = (from_ or 1) - 1
        end = start + count if count is not None else None
        # _user_status 已按 id 升序，反转成降序模拟 CF API
        sorted_desc = sorted(self._user_status, key=lambda s: s["id"], reverse=True)
        return sorted_desc[start:end]

    async def user_rating(self, handle):  # type: ignore[no-untyped-def]
        return self._user_rating

    async def user_info(self, handle):  # type: ignore[no-untyped-def]
        return [{"handle": handle, "rating": 1500}]


async def run() -> int:
    """执行验证流程，返回 0 表示成功，非 0 表示失败。"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    failures: list[str] = []

    try:
        async with factory() as session:
            async with session.begin():
                user_id = uuid4()
                handle = "mock_user_" + uuid4().hex[:8]
                account = CodeforcesAccount(id=uuid4(), user_id=user_id, handle=handle)
                session.add(account)
                logger.info("Created CodeforcesAccount: user_id=%s handle=%s", user_id, handle)

                client = FakeCFClient()

                # 1. problemset 同步
                r1 = await sync_problemset(session, client)
                logger.info("sync_problemset: %s", r1)
                assert r1["synced"] == 2, f"problemset synced != 2: {r1}"
                assert r1["total"] == 2, f"problemset total != 2: {r1}"

                cf_problems = (
                    (await session.execute(select(Problem).where(Problem.source == ProblemSource.CODEFORCES)))
                    .scalars()
                    .all()
                )
                assert len(cf_problems) >= 2, f"CF problems < 2: {len(cf_problems)}"
                logger.info("CF problems in DB: %d", len(cf_problems))

                # 2. user.status 同步
                r2 = await sync_user_status(session, account, client)
                logger.info("sync_user_status: %s", r2)
                assert r2["new_submissions"] == 2, f"new_submissions != 2: {r2}"
                assert r2["new_ac"] == 1, f"new_ac != 1: {r2}"
                assert account.last_submission_id == 9002, "cursor should be 9002"
                assert account.current_rating is None  # rating 由 sync_user_rating 更新

                subs = (await session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
                assert len(subs) == 2, f"submissions != 2: {len(subs)}"
                # 不存源代码
                for s in subs:
                    assert not hasattr(s, "source_code"), "Submission has source_code field!"
                    assert not hasattr(s, "code"), "Submission has code field!"

                # OK 写入 UserProblemAC
                acs = (
                    (await session.execute(select(UserProblemAC).where(UserProblemAC.user_id == user_id)))
                    .scalars()
                    .all()
                )
                assert len(acs) == 1, f"UserProblemAC != 1: {len(acs)}"
                logger.info("UserProblemAC created: %d", len(acs))

                # 3. user.rating 同步
                r3 = await sync_user_rating(session, account, client)
                logger.info("sync_user_rating: %s", r3)
                assert r3["new_ratings"] == 1, f"new_ratings != 1: {r3}"
                assert account.current_rating == 1500, f"current_rating != 1500: {account.current_rating}"

                rh = (
                    (await session.execute(select(RatingHistory).where(RatingHistory.user_id == user_id)))
                    .scalars()
                    .all()
                )
                assert len(rh) == 1, f"RatingHistory != 1: {len(rh)}"

                # 4. 重复同步幂等
                r1b = await sync_problemset(session, client)
                r2b = await sync_user_status(session, account, client)
                r3b = await sync_user_rating(session, account, client)
                logger.info("Idempotent re-sync: %s / %s / %s", r1b, r2b, r3b)
                # 幂等：不应有新增
                assert r2b["new_submissions"] == 0, f"repeated sync new_submissions != 0: {r2b}"
                assert r2b["new_ac"] == 0, f"repeated sync new_ac != 0: {r2b}"
                assert r3b["new_ratings"] == 0, f"repeated sync new_ratings != 0: {r3b}"

                subs_after = (
                    (await session.execute(select(Submission).where(Submission.user_id == user_id))).scalars().all()
                )
                acs_after = (
                    (await session.execute(select(UserProblemAC).where(UserProblemAC.user_id == user_id)))
                    .scalars()
                    .all()
                )
                rh_after = (
                    (await session.execute(select(RatingHistory).where(RatingHistory.user_id == user_id)))
                    .scalars()
                    .all()
                )
                assert len(subs_after) == 2, f"submissions after re-sync != 2: {len(subs_after)}"
                assert len(acs_after) == 1, f"UserProblemAC after re-sync != 1: {len(acs_after)}"
                assert len(rh_after) == 1, f"RatingHistory after re-sync != 1: {len(rh_after)}"

                logger.info("Idempotent re-sync verified: no duplicates")

                # 5. progress overview 验证
                overview = await get_progress_overview(session, user_id)
                assert isinstance(overview, ProgressOverviewResponse), "overview type mismatch"
                # streak_days：今天有提交，应该 >= 1
                assert overview.streak_days >= 1, f"streak_days < 1: {overview.streak_days}"
                # rating_history 非空
                assert len(overview.rating_history) == 1, f"rating_history != 1: {len(overview.rating_history)}"
                assert overview.rating_history[0].rating == 1500, (
                    f"rating[0] != 1500: {overview.rating_history[0].rating}"
                )
                logger.info(
                    "progress overview OK: streak_days=%d rating_history=%d solved_problems=%d",
                    overview.streak_days,
                    len(overview.rating_history),
                    overview.solved_problems,
                )

                logger.info("=" * 60)
                logger.info("ALL MANUAL SYNC VERIFICATION CHECKS PASSED")
                logger.info("=" * 60)
                return 0

    except Exception as e:
        logger.exception("Manual sync verification FAILED")
        failures.append(str(e))
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    rc = asyncio.run(run())
    sys.exit(rc)
