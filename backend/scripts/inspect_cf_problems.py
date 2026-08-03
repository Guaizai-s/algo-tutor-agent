"""检查开发库里 CF 题目分布。"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.problem import Problem, ProblemSource


async def main() -> None:
    eng = create_async_engine(settings.DATABASE_URL)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as s:
        rows = (
            await s.execute(
                select(Problem.id, Problem.cf_contest_id, Problem.cf_index, Problem.slug, Problem.title).where(
                    Problem.source == ProblemSource.CODEFORCES
                )
            )
        ).all()
        print(f"Total CF problems: {len(rows)}")
        for r in rows:
            print(f"  cf_contest_id={r.cf_contest_id} cf_index={r.cf_index} slug={r.slug} title={r.title[:30]}")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
