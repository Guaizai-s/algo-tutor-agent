"""获取最新 CodeforcesAccount.user_id 用于 HTTP 回归验证。"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.codeforces import CodeforcesAccount


async def main() -> None:
    eng = create_async_engine(settings.DATABASE_URL)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as s:
        acc = (
            await s.execute(select(CodeforcesAccount.user_id).order_by(CodeforcesAccount.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        print(acc if acc else "NO_ACCOUNT")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
