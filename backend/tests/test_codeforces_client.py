"""Codeforces API 客户端测试 (Task 8.1)。

覆盖：
- 限流和指数退避
- 永久错误不重试
- 4xx / 429 / 5xx / 网络错误处理
- problemset / user.status / user.rating / user.info 调用
- 不依赖真实 Codeforces 网络（mock httpx）
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.codeforces.client import (
    CodeforcesClient,
    CodeforcesPermanentError,
    CodeforcesTransientError,
)


def _make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> httpx.Response:
    """构造 httpx.Response mock。"""
    if json_data is not None:
        return httpx.Response(status_code=status_code, json=json_data)
    return httpx.Response(status_code=status_code, text=text)


@pytest.mark.asyncio
async def test_problemset_problems_success():
    """problemset.problems 正常调用返回 result。"""
    mock_redis = AsyncMock()
    # 限流锁可立即获取
    mock_redis.set = AsyncMock(side_effect=[True, True])

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,  # 测试中加速
        max_retries=2,
    )

    mock_response = _make_response(
        200,
        {
            "status": "OK",
            "result": {
                "problems": [{"contestId": 1, "index": "A", "name": "Test", "tags": ["dp"]}],
                "problemStatistics": [],
            },
        },
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await client.problemset_problems()

    assert "problems" in result
    assert result["problems"][0]["contestId"] == 1


@pytest.mark.asyncio
async def test_429_triggers_backoff_and_retry():
    """429 Too Many Requests 触发退避并重试，最终成功。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=3,
    )
    # mock 退避为 0 加速测试
    with patch.object(client, "_backoff", new=AsyncMock(return_value=None)):
        # 第一次 429，第二次 200
        responses = [
            _make_response(429, text="rate limit"),
            _make_response(200, {"status": "OK", "result": []}),
        ]
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=responses)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await client.user_rating("test_handle")

    assert result == []


@pytest.mark.asyncio
async def test_5xx_triggers_retry():
    """5xx 错误触发重试。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=2,
    )
    with patch.object(client, "_backoff", new=AsyncMock(return_value=None)):
        responses = [
            _make_response(503, text="service unavailable"),
            _make_response(200, {"status": "OK", "result": [{"contestId": 1}]}),
        ]
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=responses)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await client.user_rating("handle")

    assert result == [{"contestId": 1}]


@pytest.mark.asyncio
async def test_4xx_permanent_error_no_retry():
    """4xx 客户端错误不重试，直接抛 CodeforcesPermanentError。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=3,
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_make_response(400, text="bad request"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(CodeforcesPermanentError):
            await client.user_status("handle")


@pytest.mark.asyncio
async def test_invalid_handle_permanent_error():
    """CF API 返回 handle not found 视为永久错误，不重试。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=3,
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_make_response(
                200,
                {"status": "FAILED", "comment": "handle not found"},
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(CodeforcesPermanentError):
            await client.user_info("nonexistent_handle")


@pytest.mark.asyncio
async def test_network_error_triggers_retry():
    """网络错误（httpx.NetworkError）触发重试。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=2,
    )

    with patch.object(client, "_backoff", new=AsyncMock(return_value=None)):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            # 第一次网络错误，第二次成功
            mock_client.get = AsyncMock(
                side_effect=[
                    httpx.ConnectError("connection refused"),
                    _make_response(200, {"status": "OK", "result": []}),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await client.user_rating("handle")

    assert result == []


@pytest.mark.asyncio
async def test_retry_exhausted_raises_transient_error():
    """重试耗尽后抛 CodeforcesTransientError。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=1,  # 总尝试 2 次
    )

    with patch.object(client, "_backoff", new=AsyncMock(return_value=None)):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_make_response(503, text="service unavailable"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with pytest.raises(CodeforcesTransientError):
                await client.user_rating("handle")


@pytest.mark.asyncio
async def test_timeout_triggers_retry():
    """超时触发重试。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=2,
    )

    with patch.object(client, "_backoff", new=AsyncMock(return_value=None)):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=[
                    httpx.ReadTimeout("read timeout"),
                    _make_response(200, {"status": "OK", "result": []}),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await client.user_rating("handle")

    assert result == []


@pytest.mark.asyncio
async def test_rate_limit_waits_for_interval():
    """限流：距上次调用不足 min_interval 时会 sleep。"""
    mock_redis = AsyncMock()
    # 第一次 set 返回 True（获得锁）
    mock_redis.set = AsyncMock(return_value=True)
    # 模拟上次调用时间戳是 0.5 秒前
    loop_time = asyncio.get_event_loop().time()
    mock_redis.get = AsyncMock(return_value=str(loop_time - 0.5))

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=2.0,
        max_retries=1,
    )

    slept_seconds: list[float] = []

    async def mock_sleep(seconds: float) -> None:
        slept_seconds.append(seconds)
        # 不真正 sleep，只记录
        return None

    with patch("asyncio.sleep", new=mock_sleep):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_make_response(200, {"status": "OK", "result": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await client.user_rating("handle")

    # 应该至少有一次 sleep > 0（限流等待）
    assert any(s > 0 for s in slept_seconds), f"Expected rate limit sleep, got {slept_seconds}"


@pytest.mark.asyncio
async def test_user_status_with_count():
    """user.status 正确传递 count 参数。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=1,
    )

    captured_params: dict = {}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()

        async def capture_get(url, params=None, **kwargs):  # type: ignore[no-untyped-def]
            captured_params.update(params or {})
            return _make_response(200, {"status": "OK", "result": [{"id": 1}]})

        mock_client.get = capture_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await client.user_status("test_handle", count=100)

    assert captured_params["handle"] == "test_handle"
    assert captured_params["count"] == 100
    assert result == [{"id": 1}]


@pytest.mark.asyncio
async def test_user_info_passes_handles_param():
    """user.info 正确传递 handles 参数。"""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    client = CodeforcesClient(
        redis=mock_redis,
        min_interval_sec=0.01,
        max_retries=1,
    )

    captured_params: dict = {}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()

        async def capture_get(url, params=None, **kwargs):  # type: ignore[no-untyped-def]
            captured_params.update(params or {})
            return _make_response(200, {"status": "OK", "result": [{"handle": "test"}]})

        mock_client.get = capture_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await client.user_info("test_handle")

    assert captured_params["handles"] == "test_handle"
    assert result == [{"handle": "test"}]
