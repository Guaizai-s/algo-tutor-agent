"""清理手动同步验证脚本在数据库中留下的测试数据。

安全清理策略：
  - 只删除 handle 以 MOCK_HANDLE_PREFIX = "mock_user_" 开头的 CodeforcesAccount
  - 级联删除这些账号的 Submission / RatingHistory / UserProblemAC（仅关联到 CF 题的 AC）
  - 只删除 slug 以 "cf-100-" / "cf-101-" 开头的 CF 题目（验证脚本固定用这两组 contestId）

正式环境的 CF 账号 handle 不会以 "mock_user_" 开头，正式 CF 题目也不会用 100/101
这种小 contestId，因此本脚本是安全的。

使用方法：
    docker compose exec backend python -m scripts.cleanup_cf_test_data
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.learning import UserProblemAC
from app.models.problem import Problem, ProblemSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 验证脚本插入的 handle 前缀（见 verify_cf_sync_manual.py）
MOCK_HANDLE_PREFIX = "mock_user_"
# 验证脚本使用的 CF contestId（mock 数据，不会与真实 CF contest 冲突）
# 与 verify_cf_sync_manual.py 中使用的 contest_id 保持一致
MOCK_CF_CONTEST_IDS = [900001, 900002]


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # 1. 找出所有 mock 测试账号（handle 以 mock_user_ 开头）
            mock_account_user_ids = (
                (
                    await session.execute(
                        select(CodeforcesAccount.user_id).where(CodeforcesAccount.handle.like(f"{MOCK_HANDLE_PREFIX}%"))
                    )
                )
                .scalars()
                .all()
            )
            logger.info("Found %d mock CF accounts to clean", len(mock_account_user_ids))

            if not mock_account_user_ids:
                logger.info("No mock data found, nothing to clean.")
                return

            # 2. 找出 mock 账号关联的 CF 题目 id（contest_id 在 MOCK_CF_CONTEST_IDS 中）
            mock_problem_ids = (
                (
                    await session.execute(
                        select(Problem.id).where(
                            Problem.source == ProblemSource.CODEFORCES,
                            Problem.cf_contest_id.in_(MOCK_CF_CONTEST_IDS),
                        )
                    )
                )
                .scalars()
                .all()
            )
            logger.info("Found %d mock CF problems to clean", len(mock_problem_ids))

            # 3. 删除关联到 mock 题目的 UserProblemAC
            if mock_problem_ids:
                r1 = await session.execute(delete(UserProblemAC).where(UserProblemAC.problem_id.in_(mock_problem_ids)))
                logger.info("Deleted %d UserProblemAC rows", r1.rowcount)

            # 4. 删除 mock 账号的 Submission
            r2 = await session.execute(delete(Submission).where(Submission.user_id.in_(mock_account_user_ids)))
            logger.info("Deleted %d Submission rows", r2.rowcount)

            # 5. 删除 mock 账号的 RatingHistory
            r3 = await session.execute(delete(RatingHistory).where(RatingHistory.user_id.in_(mock_account_user_ids)))
            logger.info("Deleted %d RatingHistory rows", r3.rowcount)

            # 6. 删除 mock CodeforcesAccount
            r4 = await session.execute(
                delete(CodeforcesAccount).where(CodeforcesAccount.handle.like(f"{MOCK_HANDLE_PREFIX}%"))
            )
            logger.info("Deleted %d CodeforcesAccount rows", r4.rowcount)

            # 7. 删除 mock CF Problem
            r5 = await session.execute(
                delete(Problem).where(
                    Problem.source == ProblemSource.CODEFORCES,
                    Problem.cf_contest_id.in_(MOCK_CF_CONTEST_IDS),
                )
            )
            logger.info("Deleted %d CF Problem rows", r5.rowcount)

    await engine.dispose()
    logger.info("Cleanup done.")


if __name__ == "__main__":
    asyncio.run(main())
