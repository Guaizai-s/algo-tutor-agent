"""Codeforces API 客户端 (Task 8.1)。

特性：
- httpx AsyncClient 实现，连接和读取超时独立配置
- 全局速率限制 >= 2 秒/次，跨 Celery worker 通过 Redis 共享令牌桶
- 指数退避 + jitter，针对网络错误 / 429 / 5xx / 可重试 CF API 错误
- 永久错误（4xx 参数错误、无效 handle）不重试
- 明确异常类型 + 结构化日志（不泄露敏感配置）
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis 限流键：使用 SET NX + EX 实现"距上次请求至少 N 秒"
CF_RATE_LIMIT_KEY = "cf_api:last_call_ts"
# 令牌桶持有者锁，避免多 worker 同时通过限流
CF_RATE_LIMIT_LOCK_KEY = "cf_api:rate_lock"


class CodeforcesAPIError(Exception):
    """CF API 业务错误（status != OK）。"""


class CodeforcesPermanentError(CodeforcesAPIError):
    """永久错误：4xx 参数错误、无效 handle 等，不应重试。"""


class CodeforcesTransientError(CodeforcesAPIError):
    """可重试错误：5xx / 网络错误 / CF 内部错误 / 429。"""


class CodeforcesRateLimitError(CodeforcesAPIError):
    """速率限制等待超时（仅在限流无法获得时抛出，正常情况下会等待）。"""


class CodeforcesClient:
    """Codeforces API 客户端。

    所有方法均为 async，返回 dict（CF API 的 result 字段）。
    通过 Redis 共享速率限制状态，保证多 worker 之间间隔 >= 2 秒。
    """

    def __init__(
        self,
        redis: Redis | None = None,
        *,
        base_url: str | None = None,
        min_interval_sec: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._redis = redis
        self._base_url = base_url or settings.CF_API_BASE_URL
        self._min_interval = min_interval_sec or settings.CF_API_MIN_INTERVAL_SEC
        self._max_retries = max_retries if max_retries is not None else settings.CF_API_MAX_RETRIES

    async def _acquire_rate_limit(self) -> None:
        """通过 Redis 实现跨 worker 共享的速率限制。

        使用 SET NX + EX 模式：记录上次请求时间戳，若距上次不足 min_interval 则 sleep。
        为避免多个 worker 同时 sleep 后又同时请求，使用 SETNX 抢占式锁。
        """
        if self._redis is None:
            # 测试或单进程模式下退化为 asyncio.sleep
            await asyncio.sleep(self._min_interval)
            return

        # 抢占式获取限流锁：保证只有一个 worker 在等待
        # SET lock 1 NX EX <min_interval * 2>
        acquired = await self._redis.set(
            CF_RATE_LIMIT_LOCK_KEY,
            "1",
            nx=True,
            ex=int(self._min_interval * 2) + 1,
        )
        if not acquired:
            # 其他 worker 正在等待，本请求排队等待锁释放
            # 轮询锁状态，最长等待 30 秒
            for _ in range(60):
                acquired = await self._redis.set(
                    CF_RATE_LIMIT_LOCK_KEY,
                    "1",
                    nx=True,
                    ex=int(self._min_interval * 2) + 1,
                )
                if acquired:
                    break
                await asyncio.sleep(0.5)
            else:
                raise CodeforcesRateLimitError("等待 CF API 速率限制锁超时（30s）")

        try:
            # 读取上次调用时间戳
            last_ts = await self._redis.get(CF_RATE_LIMIT_KEY)
            # Redis 中的值会跨进程、跨容器重启复用，必须使用可比较的 Unix 墙钟。
            # event_loop.time() 的基准只保证在当前进程内稳定，重启后会导致负 elapsed
            # 和超长错误等待。
            now = time.time()
            if last_ts is not None:
                elapsed = now - float(last_ts)
                wait = self._min_interval - elapsed
                if wait > 0:
                    logger.debug("CF API rate limit: waiting %.2fs", wait)
                    await asyncio.sleep(wait)
            # 更新最后调用时间戳
            await self._redis.set(CF_RATE_LIMIT_KEY, str(time.time()))
        finally:
            await self._redis.delete(CF_RATE_LIMIT_LOCK_KEY)

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        """发起 CF API 请求，自动速率限制 + 指数退避。

        Args:
            method: CF API 方法名（如 "problemset.problems"）
            params: 查询参数

        Returns:
            CF API 响应的 result 字段

        Raises:
            CodeforcesPermanentError: 4xx / handle 无效等不可重试错误
            CodeforcesTransientError: 重试耗尽后的最终错误
        """
        url = f"{self._base_url}/{method}"
        timeout = httpx.Timeout(
            connect=settings.CF_API_CONNECT_TIMEOUT_SEC,
            read=settings.CF_API_READ_TIMEOUT_SEC,
            write=10.0,
            pool=5.0,
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._acquire_rate_limit()
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.get(url, params=params)

                if resp.status_code == 429:
                    # 速率限制被 CF 主动拒绝，必须退避
                    last_exc = CodeforcesTransientError(f"CF API 429 Too Many Requests: {method}")
                    logger.warning("CF API 429 on %s, attempt %d", method, attempt + 1)
                    await self._backoff(attempt)
                    continue

                if 500 <= resp.status_code < 600:
                    last_exc = CodeforcesTransientError(f"CF API {resp.status_code} server error: {method}")
                    logger.warning("CF API %d on %s, attempt %d", resp.status_code, method, attempt + 1)
                    await self._backoff(attempt)
                    continue

                if 400 <= resp.status_code < 500:
                    # 永久错误：参数错误、handle 无效等，不重试
                    raise CodeforcesPermanentError(f"CF API {resp.status_code} client error: {resp.text[:200]}")

                data = resp.json()
                if data.get("status") != "OK":
                    comment = data.get("comment", "")
                    # CF API 错误评论中包含 'not found' / 'invalid' 通常是永久错误
                    lower = comment.lower()
                    if "not found" in lower or "invalid" in lower or "argument" in lower:
                        raise CodeforcesPermanentError(f"CF API returned status={data.get('status')}: {comment}")
                    # 其他错误（如 'Call limit exceeded'）可重试
                    last_exc = CodeforcesTransientError(f"CF API returned status={data.get('status')}: {comment}")
                    logger.warning("CF API non-OK on %s: %s, attempt %d", method, comment, attempt + 1)
                    await self._backoff(attempt)
                    continue

                return data["result"]

            except httpx.TimeoutException as exc:
                last_exc = CodeforcesTransientError(f"CF API timeout: {exc}")
                logger.warning("CF API timeout on %s, attempt %d: %s", method, attempt + 1, exc)
                await self._backoff(attempt)
            except httpx.NetworkError as exc:
                last_exc = CodeforcesTransientError(f"CF API network error: {exc}")
                logger.warning("CF API network error on %s, attempt %d: %s", method, attempt + 1, exc)
                await self._backoff(attempt)

        # 重试耗尽
        raise last_exc or CodeforcesTransientError(f"CF API retries exhausted on {method}")

    async def _backoff(self, attempt: int) -> None:
        """指数退避 + jitter。

        base * 2^attempt，上限 max_backoff，加 0~50% jitter。
        """
        base = settings.CF_API_BACKOFF_BASE_SEC
        max_wait = settings.CF_API_BACKOFF_MAX_SEC
        wait = min(base * (2**attempt), max_wait)
        jitter = random.uniform(0, wait * 0.5)
        total = wait + jitter
        logger.debug("CF API backoff: %.2fs (attempt %d)", total, attempt + 1)
        await asyncio.sleep(total)

    # ===== CF API 方法 =====

    async def problemset_problems(self, tags: list[str] | None = None) -> dict[str, Any]:
        """GET /problemset.problems

        Returns:
            {"problems": [...], "problemStatistics": [...]}
        """
        params: dict[str, Any] = {}
        if tags:
            params["tags"] = ";".join(tags)
        return await self._request("problemset.problems", params)

    async def user_status(
        self,
        handle: str,
        *,
        from_: int | None = None,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET /user.status

        CF API 返回按 submission id 降序（最新在前）。
        通过 from + count 实现真正的分页：from 是 1-based 索引。

        Args:
            handle: CF 用户名
            from_: 1-based 起始索引（默认 1，即从最新开始）
            count: 限制返回数量；与 from_ 配合用于分页

        Returns:
            submission 列表（最新在前）
        """
        params: dict[str, Any] = {"handle": handle}
        if from_ is not None:
            params["from"] = from_
        if count is not None:
            params["count"] = count
        return await self._request("user.status", params)

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        """GET /user.rating

        Returns:
            rating 变更历史列表（按时间升序）
        """
        return await self._request("user.rating", {"handle": handle})

    async def user_info(self, handle: str) -> list[dict[str, Any]]:
        """GET /user.info —— 用于验证 handle 是否存在。

        Returns:
            单元素列表（用户信息）
        """
        return await self._request("user.info", {"handles": handle})


def _create_redis() -> Redis | None:
    """从 settings.REDIS_URL 创建 Redis 连接，失败时返回 None（退化为单进程限流）。

    注意：返回的 Redis 连接绑定到调用时所在的事件循环。调用方必须在同一事件循环内
    使用并负责 await redis.aclose()。不要跨事件循环缓存。
    """
    try:
        return Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:  # pragma: no cover - 仅在 Redis 不可达时触发
        logger.warning("CF client: Redis unavailable, falling back to per-process rate limit: %s", exc)
        return None


def get_codeforces_client(redis: Redis | None = None, *, use_redis: bool = True) -> CodeforcesClient:
    """创建 CF API 客户端工厂。

    每次调用返回一个新的 CodeforcesClient 实例，绑定到调用方的事件循环。
    不缓存跨事件循环的异步 Redis 连接 —— Celery worker 每个任务用 asyncio.run() 创建
    独立事件循环，复用旧 loop 的 Redis 连接会抛 "Future attached to a different loop"。

    生产路径（Celery worker / FastAPI）：
        - 不传 redis 参数时，自动从 settings.REDIS_URL 初始化新的 Redis 连接，
          保证多 worker 之间共享速率限制（>= 2 秒/次）。
        - 调用方负责在事件循环结束前 await redis.aclose()（cf_tasks._run_with_session 已处理）。

    测试路径：
        - 传入 redis 参数（含 None）覆盖；传 use_redis=False 可强制禁用 Redis。
    """
    effective_redis = redis
    if use_redis and effective_redis is None:
        effective_redis = _create_redis()
    return CodeforcesClient(redis=effective_redis)


async def close_codeforces_client(client: CodeforcesClient) -> None:
    """关闭 CodeforcesClient 持有的 Redis 连接。

    必须在创建 client 的同一事件循环内调用。Celery 任务在 _run_with_session 的
    finally 中调用此函数，避免跨 loop 复用。

    对测试注入的 fake client（无 _redis 属性）是 no-op。
    """
    redis = getattr(client, "_redis", None)
    if redis is not None:
        try:
            await redis.aclose()
        except Exception as exc:  # pragma: no cover
            logger.warning("CF client: Redis close error: %s", exc)
