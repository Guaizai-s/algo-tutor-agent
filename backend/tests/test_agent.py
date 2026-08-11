"""Agent flow tests using mocked OpenAI client.

These tests verify the tool-calling loop without hitting the real OpenAI API
or Docker sandbox.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.agents.tutor_agent import TutorAgent
from app.schemas.agent import AgentChatRequest


class _ToolCall:
    def __init__(self, name: str, args: dict[str, Any]):
        self.id = f"call_{name}"
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = json.dumps(args)


class _Message:
    def __init__(self, content: str | None, tool_calls: list[_ToolCall] | None = None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: _Message):
        self.message = message


class _Resp:
    def __init__(self, choices: list[_Choice]):
        self.choices = choices


def _make_openai_mock(responses: list[_Resp]) -> Any:
    """Build a fake OpenAIService with an AsyncMock client."""
    svc = MagicMock()
    svc.client = MagicMock()
    # chat.completions.create is awaited; use side_effect of async fns.
    create_mock = AsyncMock()
    create_mock.side_effect = responses
    svc.client.chat.completions.create = create_mock
    return svc


@pytest.mark.asyncio
async def test_agent_plain_answer(db_session, seed_data):
    """Test 1: Agent returns a plain answer without tool calls."""
    from app.services.rag import RAGService

    rag = RAGService.__new__(RAGService)
    rag._session_factory = None  # type: ignore[attr-defined]
    rag._openai = None
    rag._pgvector_available = False

    openai_svc = _make_openai_mock([_Resp([_Choice(_Message(content="动态规划是记住子问题解以避免重复计算的方法。"))])])

    agent = TutorAgent(openai_svc, _DummyFactory(db_session), rag)  # type: ignore[arg-type]
    req = AgentChatRequest(message="什么是动态规划？")
    resp = await agent.run(req)
    assert "动态规划" in resp.message
    assert resp.tool_calls == []


@pytest.mark.asyncio
async def test_agent_injects_authenticated_learning_context(
    db_session,
    seed_data,
    auth_user,
):
    """OpenAI system prompt receives server-side target and weak-point context, not email."""
    from app.models.learning import LearningProfile, UserKnowledgeState
    from app.services.rag import RAGService

    user = auth_user["user"]
    db_session.add(
        LearningProfile(
            user_id=user.id,
            target_rating_min=1600,
            target_rating_max=2000,
        )
    )
    db_session.add(
        UserKnowledgeState(
            user_id=user.id,
            knowledge_id=seed_data["knowledge_point_id"],
            mastery=0.25,
            is_weak=True,
            consecutive_wa=3,
        )
    )
    await db_session.flush()

    rag = RAGService.__new__(RAGService)
    rag._session_factory = None  # type: ignore[attr-defined]
    rag._openai = None
    rag._pgvector_available = False
    openai_svc = _make_openai_mock([_Resp([_Choice(_Message(content="个性化建议"))])])
    agent = TutorAgent(
        openai_svc,
        _DummyFactory(db_session),  # type: ignore[arg-type]
        rag,
        user_id=user.id,
    )

    await agent.run(AgentChatRequest(message="我今天学什么？"))

    call = openai_svc.client.chat.completions.create.await_args
    system_prompt = call.kwargs["messages"][0]["content"]
    assert "目标 Rating：1600-2000" in system_prompt
    assert "薄弱点" in system_prompt
    assert "掌握度 25%" in system_prompt
    assert user.email not in system_prompt


@pytest.mark.asyncio
async def test_agent_endpoint_requires_authentication(client):
    response = await client.post("/api/v1/agent/chat", json={"message": "解释二分查找"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_daily_quota(monkeypatch):
    from app.core.config import settings
    from app.services.agent_quota import AgentQuotaExceededError, consume_agent_quota

    class FakeRedis:
        def __init__(self):
            self.used = 0

        async def eval(self, script, key_count, key, ttl):
            self.used += 1
            return self.used

    fake = FakeRedis()
    monkeypatch.setattr(settings, "AGENT_DAILY_REQUEST_LIMIT", 2)

    assert await consume_agent_quota(UUID(int=1), fake) == (1, 2)  # type: ignore[arg-type]
    assert await consume_agent_quota(UUID(int=1), fake) == (2, 2)  # type: ignore[arg-type]
    with pytest.raises(AgentQuotaExceededError):
        await consume_agent_quota(UUID(int=1), fake)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_agent_calls_problem_search(db_session, seed_data):
    """Test 2: Agent triggers search_problems and surfaces references."""
    from app.services.rag import RAGService

    rag = RAGService.__new__(RAGService)
    rag._session_factory = None  # type: ignore[attr-defined]
    rag._openai = None
    rag._pgvector_available = False

    openai_svc = _make_openai_mock(
        [
            # Round 1: model asks to search problems.
            _Resp(
                [
                    _Choice(
                        _Message(
                            content=None, tool_calls=[_ToolCall("search_problems", {"query": "测试题目", "limit": 5})]
                        )
                    )
                ]
            ),
            # Round 2: model gives final answer.
            _Resp([_Choice(_Message(content="找到了相关题目，参见引用。"))]),
        ]
    )

    agent = TutorAgent(openai_svc, _DummyFactory(db_session), rag)  # type: ignore[arg-type]
    req = AgentChatRequest(message="推荐一道题")
    resp = await agent.run(req)
    assert any(tc.name == "search_problems" and tc.status == "success" for tc in resp.tool_calls)
    assert any(r.type == "problem" for r in resp.references)


@pytest.mark.asyncio
async def test_agent_calls_knowledge_search(db_session, seed_data):
    """Test 3: Agent triggers search_knowledge and returns references.

    RAGService must share the test db_session so it can read seed_data inside
    the uncommitted transaction. Using an independent engine/session would
    not see seed_data and the keyword fallback would return [].
    """
    from app.services.rag import RAGService

    # Reuse the test session via _DummyFactory so RAG reads seed_data inside
    # the same uncommitted transaction.
    factory = _DummyFactory(db_session)
    rag = RAGService(factory, openai_svc=None)  # type: ignore[arg-type]
    rag._pgvector_available = False  # force keyword fallback

    openai_svc = _make_openai_mock(
        [
            _Resp(
                [
                    _Choice(
                        _Message(
                            content=None,
                            tool_calls=[_ToolCall("search_knowledge", {"query": "动态规划", "limit": 5})],
                        )
                    )
                ]
            ),
            _Resp([_Choice(_Message(content="知识库中有相关讲义，参见引用。"))]),
        ]
    )

    agent = TutorAgent(openai_svc, factory, rag)  # type: ignore[arg-type]
    req = AgentChatRequest(message="解释动态规划")
    resp = await agent.run(req)
    assert any(tc.name == "search_knowledge" for tc in resp.tool_calls)
    # keyword fallback should find our seeded lecture.
    assert any(r.type == "knowledge" for r in resp.references)


@pytest.mark.asyncio
async def test_tool_exception_does_not_raise_500(db_session, seed_data):
    """Test 7: tool internal exception is captured, returns error tool_call."""
    import app.tools.code_execution as ce
    from app.services.rag import RAGService

    rag = RAGService.__new__(RAGService)
    rag._session_factory = None  # type: ignore[attr-defined]
    rag._openai = None
    rag._pgvector_available = False

    # Force code_execution.execute to raise.
    original = ce.execute

    async def _boom(_params):
        raise RuntimeError("simulated")

    ce.execute = _boom  # type: ignore[assignment]

    openai_svc = _make_openai_mock(
        [
            _Resp(
                [
                    _Choice(
                        _Message(
                            content=None,
                            tool_calls=[_ToolCall("execute_code", {"language": "python", "code": "print(1)"})],
                        )
                    )
                ]
            ),
            _Resp([_Choice(_Message(content="代码执行失败，原因：tool_exception"))]),
        ]
    )

    try:
        agent = TutorAgent(openai_svc, _DummyFactory(db_session), rag)  # type: ignore[arg-type]
        req = AgentChatRequest(message="执行这段代码", context={"language": "python", "code": "print(1)"})
        resp = await agent.run(req)
        # Agent should have returned normally, with an error tool_call.
        assert any(tc.name == "execute_code" and tc.status == "error" for tc in resp.tool_calls)
    finally:
        ce.execute = original  # type: ignore[assignment]


class _DummyFactory:
    """A minimal async_sessionmaker substitute that returns the test session."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _CtxManager(self._session)


class _CtxManager:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False
