"""Pytest configuration and fixtures.

Uses a real PostgreSQL database (pgvector requires PG). Tests MUST run
against an isolated scratch DB to avoid polluting the dev database:
set TEST_DATABASE_URL explicitly. If unset, the suite aborts with a clear
error explaining how to provision a test DB.

Event loop / asyncpg alignment:
- We do NOT override the event_loop fixture. pytest-asyncio with
  asyncio_default_fixture_loop_scope=function (set in pytest.ini) gives
  each test a function-scoped loop.
- The DB engine fixture is also function-scoped, so engine + session +
  test all share the SAME loop. This avoids "Future attached to a
  different loop" / "Event loop is closed" errors that previously
  occurred when a session-scoped engine was reused across function-scoped
  loops.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _resolve_test_database_url() -> str:
    """Resolve TEST_DATABASE_URL, aborting if unset.

    Reusing the dev DATABASE_URL for tests is forbidden: it pollutes dev
    data and breaks assertions (e.g. CF problem counts).
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest_import_error = (
            "TEST_DATABASE_URL is not set. Tests must run against an isolated "
            "scratch database, not the dev DATABASE_URL. Provision a test DB "
            "(e.g. createdb algo_tutor_test) and export "
            "TEST_DATABASE_URL=postgresql+asyncpg://user:pwd@host:port/algo_tutor_test"
        )
        raise RuntimeError(pytest_import_error)
    return url


TEST_DATABASE_URL = _resolve_test_database_url()


@pytest_asyncio.fixture
async def test_engine():
    """Function-scoped async engine.

    NullPool avoids asyncpg connection reuse across tests. Function scope
    guarantees the engine's connections bind to the test's own event loop,
    preventing cross-loop errors.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test session inside a transaction that is rolled back.

    Uses an outer transaction (session.begin()) and rolls back before the
    context manager exits, so test data is never committed to the DB.
    This keeps tests isolated without needing per-test DB cleanup.
    """
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            # Force rollback before the context manager commits.
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with get_db overridden to the test session."""
    from app.core.database import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    # Also override openai_service + rag_service so we don't need a live key.
    import app.services.openai_service as openai_module
    import app.services.rag as rag_module
    from app.services.openai_service import OpenAIService

    # Save originals to restore later.
    orig_openai = openai_module.openai_service
    orig_rag = rag_module.rag_service

    openai_module.openai_service = OpenAIService.__new__(OpenAIService)
    openai_module.openai_service.client = None  # tests inject mocks
    rag_module.rag_service = rag_module.RAGService.__new__(rag_module.RAGService)
    rag_module.rag_service._session_factory = None  # type: ignore[attr-defined]
    rag_module.rag_service._openai = None
    rag_module.rag_service._pgvector_available = False

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    openai_module.openai_service = orig_openai
    rag_module.rag_service = orig_rag


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession) -> dict[str, Any]:
    """Insert a published problem + knowledge point + lecture.

    Returns dict with ids. The whole transaction is rolled back at test end.
    """
    from app.models.knowledge import KnowledgePoint, Lecture, LectureLevel
    from app.models.problem import Problem, ProblemDifficulty, ProblemStatus

    kp_id = uuid4()
    lecture_id = uuid4()
    problem_id = uuid4()

    kp = KnowledgePoint(
        id=kp_id,
        name=f"测试知识点 {kp_id}",
        slug=f"test-kp-{kp_id}",
        description="用于测试的知识点",
    )
    db_session.add(kp)
    await db_session.flush()

    lecture = Lecture(
        id=lecture_id,
        knowledge_id=kp_id,
        level=LectureLevel.STANDARD,
        title="测试讲义",
        content="动态规划的核心是状态与状态转移方程。",
    )
    db_session.add(lecture)

    problem = Problem(
        id=problem_id,
        title=f"测试题目 {problem_id}",
        slug=f"test-problem-{problem_id}",
        description="一道用于测试的题目：求两数之和。",
        difficulty=ProblemDifficulty.EASY,
        status=ProblemStatus.PUBLISHED,
        time_limit_ms=1000,
        memory_limit_kb=262144,
        sample_input="1 2",
        sample_output="3",
        hints=["使用加法"],
        solution_template=None,
        # Hidden test cases — must NEVER appear in API output.
        test_cases=[{"input": "1 2", "output": "3", "hidden": True}],
        submit_count=10,
        accepted_count=8,
    )
    problem.knowledge_points.append(kp)
    db_session.add(problem)
    await db_session.flush()

    return {
        "knowledge_point_id": kp_id,
        "lecture_id": lecture_id,
        "problem_id": problem_id,
    }
