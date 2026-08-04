"""Codeforces 同步 Celery 任务 (Task 8)。

每个任务封装 async service 调用：
- 在独立事件循环中执行 async 代码
- 使用独立的 AsyncSession 和 CodeforcesClient（含 Redis 连接）
  避免跨任务复用绑定到旧事件循环的异步资源
- 支持手动调用（通过 .delay() 或 .apply()）

注意：Celery worker 内不能复用 FastAPI 的 async_session_maker，
也不能缓存跨 asyncio.run() 调用的异步 Redis 连接。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import settings
from app.models.codeforces import CodeforcesAccount
from app.services.codeforces.client import CodeforcesClient, close_codeforces_client, get_codeforces_client
from app.services.codeforces.sync import (
    sync_all_users_rating,
    sync_all_users_status,
    sync_problemset,
    sync_user_status,
)

logger = logging.getLogger(__name__)

# 测试钩子：设置后 Celery 任务用此工厂创建 CF client（避免真实 CF API 调用）。
# 生产环境永远不设置此变量。测试通过 monkeypatch 设置并在 finally 清理。
_test_client_factory: Callable[[], CodeforcesClient] | None = None


async def _run_with_session(
    coro_factory: Callable[[AsyncSession, CodeforcesClient], Awaitable[object]],
) -> object:
    """在独立事件循环中执行 async 函数，使用独立的 engine + session + CF client。

    每次调用都创建新的 CodeforcesClient（含新的 Redis 连接），并在 finally 中
    关闭 Redis 连接，避免跨 asyncio.run() 事件循环复用导致
    "Future attached to a different loop" / "Event loop is closed" 错误。

    测试可通过设置模块级 _test_client_factory 注入 fake client（不含 Redis、
    不连真实 CF API）。生产路径不设置，默认用 get_codeforces_client()。

    Args:
        coro_factory: 接受 (AsyncSession, CodeforcesClient) 参数的 async 函数
    """
    # 每个任务独立的 engine 和 CF client，避免跨任务状态污染 / 事件循环复用
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # 测试注入优先；否则创建真实 client（含 Redis 连接），绑定到当前事件循环
    client = _test_client_factory() if _test_client_factory is not None else get_codeforces_client()
    try:
        async with factory() as session:
            async with session.begin():
                result = await coro_factory(session, client)
            return result
    finally:
        # 必须在当前事件循环内关闭 Redis 连接（fake client 的 close_codeforces_client 是 no-op）
        await close_codeforces_client(client)
        await engine.dispose()


@celery_app.task(bind=True, name="app.tasks.cf_tasks.sync_problemset_task")
def sync_problemset_task(self) -> dict:  # type: ignore[no-untyped-def]
    """Celery 任务：全量同步 CF problemset.problems（每日）。

    手动触发：
        from app.tasks.cf_tasks import sync_problemset_task
        sync_problemset_task.delay()  # 异步
        sync_problemset_task.apply()   # 同步
    """
    logger.info("Celery task: sync_problemset_task started")

    async def _run(db: AsyncSession, client: CodeforcesClient) -> dict:
        return await sync_problemset(db, client)

    result = asyncio.run(_run_with_session(_run))
    logger.info("Celery task: sync_problemset_task done: %s", result)
    return result  # type: ignore[return-value]


@celery_app.task(bind=True, name="app.tasks.cf_tasks.sync_all_users_status_task")
def sync_all_users_status_task(self) -> dict:  # type: ignore[no-untyped-def]
    """Celery 任务：同步所有已绑定 CF 账号的 user.status（每 5 分钟）。

    单个账号失败不影响其他账号，失败账号的 status="error"。

    返回值中包含 status 字段：
    - "ok"：所有账号同步成功（或无账号）
    - "partial"：部分账号失败，详情见 results
    - "error"：整体失败（如数据库连接失败）
    """
    logger.info("Celery task: sync_all_users_status_task started")

    async def _run(db: AsyncSession, client: CodeforcesClient) -> dict:
        results = await sync_all_users_status(db, client)
        failed = [r for r in results if r.get("status") == "error"]
        if failed and len(failed) == len(results):
            overall = "error"
        elif failed:
            overall = "partial"
        else:
            overall = "ok"
        return {"status": overall, "results": results}

    result = asyncio.run(_run_with_session(_run))
    logger.info(
        "Celery task: sync_all_users_status_task done: status=%s, accounts=%d",
        result.get("status"),
        len(result.get("results", [])),
    )
    return result  # type: ignore[return-value]


@celery_app.task(bind=True, name="app.tasks.cf_tasks.sync_all_users_rating_task")
def sync_all_users_rating_task(self) -> dict:  # type: ignore[no-untyped-def]
    """Celery 任务：同步所有已绑定 CF 账号的 user.rating（每日）。

    返回值中包含 status 字段：
    - "ok"：所有账号同步成功（或无账号）
    - "partial"：部分账号失败
    - "error"：整体失败
    """
    logger.info("Celery task: sync_all_users_rating_task started")

    async def _run(db: AsyncSession, client: CodeforcesClient) -> dict:
        results = await sync_all_users_rating(db, client)
        failed = [r for r in results if r.get("status") == "error"]
        if failed and len(failed) == len(results):
            overall = "error"
        elif failed:
            overall = "partial"
        else:
            overall = "ok"
        return {"status": overall, "results": results}

    result = asyncio.run(_run_with_session(_run))
    logger.info(
        "Celery task: sync_all_users_rating_task done: status=%s, accounts=%d",
        result.get("status"),
        len(result.get("results", [])),
    )
    return result  # type: ignore[return-value]


@celery_app.task(bind=True, name="app.tasks.cf_tasks.sync_single_user_status_task")
def sync_single_user_status_task(self, account_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Celery 任务：同步单个 CF 账号的 user.status（手动触发或排错）。

    Args:
        account_id: CodeforcesAccount.id (UUID 字符串)
    """
    logger.info("Celery task: sync_single_user_status_task started, account_id=%s", account_id)

    async def _run(db: AsyncSession, client: CodeforcesClient) -> dict:
        account = (
            await db.execute(select(CodeforcesAccount).where(CodeforcesAccount.id == UUID(account_id)))
        ).scalar_one_or_none()
        if account is None:
            raise ValueError(f"CodeforcesAccount {account_id} not found")
        return await sync_user_status(db, account, client)

    result = asyncio.run(_run_with_session(_run))
    logger.info("Celery task: sync_single_user_status_task done: %s", result)
    return result  # type: ignore[return-value]
