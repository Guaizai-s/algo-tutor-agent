"""Direct problem code-execution endpoint tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.problem import ProblemStatus
from app.routers.problems import execute_problem_code
from app.schemas.problem import CodeExecutionRequest
from app.services.judge import JudgeResult, Verdict


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, problem):
        self._problem = problem

    async def execute(self, _stmt):
        return _ScalarResult(self._problem)


@pytest.mark.asyncio
async def test_execute_problem_code_bypasses_agent_and_uses_sample(monkeypatch):
    problem = SimpleNamespace(
        status=ProblemStatus.PUBLISHED,
        sample_input="1 2\n",
        sample_output="3\n",
        time_limit_ms=1000,
        memory_limit_kb=262144,
    )
    judge_mock = AsyncMock(return_value=JudgeResult(verdict=Verdict.AC, stdout="3\n", time_ms=25))
    execute_mock = AsyncMock()
    monkeypatch.setattr("app.routers.problems.judge_service.judge", judge_mock)
    monkeypatch.setattr("app.routers.problems.code_execution.execute", execute_mock)

    response = await execute_problem_code(
        uuid4(),
        CodeExecutionRequest(language="python", code="print(sum(map(int, input().split())))"),
        _FakeSession(problem),
    )

    judge_mock.assert_awaited_once_with(
        source_code="print(sum(map(int, input().split())))",
        language="python",
        test_input="1 2\n",
        expected_output="3\n",
        timeout_ms=1000,
        memory_mb=256,
    )
    execute_mock.assert_not_awaited()
    assert response.status == "success"
    assert response.stdout == "3\n"
    assert response.input_source == "sample"
    assert response.verdict == "AC"
    assert response.is_real_judge is False
    assert response.passed_cases == 1
    assert response.total_cases == 1


@pytest.mark.asyncio
async def test_execute_problem_code_marks_wrong_sample_output_as_wa(monkeypatch):
    problem = SimpleNamespace(
        status=ProblemStatus.PUBLISHED,
        sample_input="1 2\n",
        sample_output="3\n",
        time_limit_ms=1000,
        memory_limit_kb=262144,
    )
    judge_mock = AsyncMock(
        return_value=JudgeResult(
            verdict=Verdict.WA,
            stdout="hello\n",
            time_ms=20,
            message="答案错误: expected=3, got=hello",
        )
    )
    monkeypatch.setattr("app.routers.problems.judge_service.judge", judge_mock)

    response = await execute_problem_code(
        uuid4(),
        CodeExecutionRequest(language="python", code="print('hello')"),
        _FakeSession(problem),
    )

    assert response.status == "success"
    assert response.verdict == "WA"
    assert response.passed_cases == 0
    assert response.total_cases == 1
    assert "样例未通过" in response.message


@pytest.mark.asyncio
async def test_execute_problem_code_prefers_explicit_custom_input(monkeypatch):
    problem = SimpleNamespace(
        status=ProblemStatus.PUBLISHED,
        sample_input="sample\n",
        sample_output="sample\n",
        time_limit_ms=1000,
        memory_limit_kb=262144,
    )
    execute_mock = AsyncMock(
        return_value={
            "status": "success",
            "stdout": "custom\n",
            "stderr": "",
            "exit_code": 0,
            "time_used_ms": 10,
            "truncated": False,
        }
    )
    monkeypatch.setattr("app.routers.problems.code_execution.execute", execute_mock)

    response = await execute_problem_code(
        uuid4(),
        CodeExecutionRequest(language="python", code="print(input())", stdin="custom\n"),
        _FakeSession(problem),
    )

    assert execute_mock.await_args.args[0]["stdin"] == "custom\n"
    assert response.input_source == "custom"


@pytest.mark.asyncio
async def test_execute_problem_code_rejects_missing_input(monkeypatch):
    from fastapi import HTTPException

    problem = SimpleNamespace(
        status=ProblemStatus.PUBLISHED,
        sample_input=None,
        time_limit_ms=1000,
        memory_limit_kb=262144,
    )
    execute_mock = AsyncMock()
    monkeypatch.setattr("app.routers.problems.code_execution.execute", execute_mock)

    with pytest.raises(HTTPException) as exc_info:
        await execute_problem_code(
            uuid4(),
            CodeExecutionRequest(language="python", code="print(input())"),
            _FakeSession(problem),
        )

    assert exc_info.value.status_code == 422
    execute_mock.assert_not_awaited()
