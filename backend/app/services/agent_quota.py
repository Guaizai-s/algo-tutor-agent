"""OpenAI Tutor 的按用户自然日调用配额。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)
SHANGHAI_TZ = timezone(timedelta(hours=8))
QUOTA_TTL_SECONDS = 60 * 60 * 48


class AgentQuotaExceededError(Exception):
    """用户当天的 Tutor 调用次数已用尽。"""


async def consume_agent_quota(
    user_id: UUID,
    redis: Redis | None = None,
) -> tuple[int, int]:
    """原子增加当日计数；Redis 故障时记录告警并保持问答可用。"""
    limit = settings.AGENT_DAILY_REQUEST_LIMIT
    if limit <= 0:
        return (0, limit)

    owns_connection = redis is None
    client = redis or Redis.from_url(settings.REDIS_URL, decode_responses=True)
    day = datetime.now(SHANGHAI_TZ).date().isoformat()
    key = f"agent:daily:{day}:{user_id}"
    script = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return current
    """
    try:
        used = int(await client.eval(script, 1, key, QUOTA_TTL_SECONDS))
    except Exception as exc:  # pragma: no cover - 仅 Redis 故障时触发
        logger.warning("agent quota unavailable, allowing request: %s", type(exc).__name__)
        return (0, limit)
    finally:
        if owns_connection:
            await client.aclose()

    if used > limit:
        raise AgentQuotaExceededError
    return (used, limit)
