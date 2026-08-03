"""Direct problem code-execution endpoint tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.problem import ProblemStatus
from app.routers.problems import execute_problem_code
from app.schemas.problem import CodeExecutionRequest


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
        time_limit_ms=1000,
        memory_limit_kb=262144,
    )
    sandbox_result = {
        "status": "success",
        "stdout": "3\n",
        "stderr": "",
        "exit_code": 0,
        "time_used_ms": 25,
        "truncated": False,
    }
    execute_mock = AsyncMock(return_value=sandbox_result)
    monkeypatch.setattr("app.routers.problems.code_execution.execute", execute_mock)

    response = await execute_problem_code(
        uuid4(),
        CodeExecutionRequest(language="python", code="print(sum(map(int, input().split())))"),
        _FakeSession(problem),
    )

    execute_mock.assert_awaited_once_with(
        {
            "language": "python",
            "code": "print(sum(map(int, input().split())))",
            "stdin": "1 2\n",
            "timeout_ms": 1000,
            "memory_limit_mb": 256,
        }
    )
    assert response.status == "success"
    assert response.stdout == "3\n"
    assert response.input_source == "sample"
