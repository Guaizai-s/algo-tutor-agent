"""Manually fetch and cache one Codeforces problem's public statement/sample.

Usage: python -m scripts.sync_cf_problem_content 2254 B
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.problem import Problem
from app.services.codeforces.content import ProblemContentError, sync_problem_content


async def run(contest_id: int, index: str) -> None:
    async with async_session_maker() as session:
        problem = (
            await session.execute(
                select(Problem).where(
                    Problem.cf_contest_id == contest_id,
                    Problem.cf_index == index.upper(),
                )
            )
        ).scalar_one_or_none()
        if problem is None:
            raise SystemExit(f"CF{contest_id}{index.upper()} is not present; run problemset sync first")

        updated = await sync_problem_content(problem, force=True)
        await session.commit()
        if not updated:
            raise ProblemContentError(f"CF{contest_id}{index.upper()} content sync failed")
        print(
            f"CF{contest_id}{index.upper()} synced: "
            f"sample_input={len(problem.sample_input or '')} chars, "
            f"sample_output={len(problem.sample_output or '')} chars"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contest_id", type=int)
    parser.add_argument("index")
    args = parser.parse_args()
    asyncio.run(run(args.contest_id, args.index))


if __name__ == "__main__":
    main()
