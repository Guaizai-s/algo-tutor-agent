"""Public Codeforces statement/sample synchronization tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.problem import ProblemSource
from app.services.codeforces.content import (
    ProblemContentError,
    content_sync_due,
    parse_luogu_problem_page,
    sync_problem_content,
)


def _page(problem: dict) -> str:
    payload = {"data": {"problem": problem}}
    return f'<script id="lentille-context" type="application/json">{json.dumps(payload)}</script>'


def test_parse_luogu_problem_page_extracts_public_content_and_limits():
    result = parse_luogu_problem_page(
        _page(
            {
                "content": {
                    "description": "Compress the string.",
                    "formatI": "Read t test cases.",
                    "formatO": "Print the minimum.",
                },
                "samples": [["1\n3\nabc", "2"]],
                "limits": {"time": [2000], "memory": [256000]},
            }
        )
    )

    assert "Compress the string." in result.description
    assert "Input\n\nRead t test cases." in result.description
    assert result.sample_input == "1\n3\nabc\n"
    assert result.sample_output == "2\n"
    assert result.time_limit_ms == 2000
    assert result.memory_limit_kb == 256000


def test_parse_luogu_problem_page_rejects_missing_sample():
    with pytest.raises(ProblemContentError):
        parse_luogu_problem_page(_page({"content": {"description": "Statement"}, "samples": []}))


def test_content_sync_due_skips_cached_content_and_recent_failure():
    cached = SimpleNamespace(
        source=ProblemSource.CODEFORCES,
        cf_contest_id=2254,
        cf_index="B",
        sample_input="input",
        sample_output="output",
        content_sync_failed_at=None,
    )
    assert content_sync_due(cached) is False

    failed = SimpleNamespace(
        source=ProblemSource.CODEFORCES,
        cf_contest_id=2254,
        cf_index="B",
        sample_input=None,
        sample_output=None,
        content_sync_failed_at=datetime.now(tz=UTC),
    )
    assert content_sync_due(failed) is False


@pytest.mark.asyncio
async def test_sync_problem_content_caches_result(monkeypatch):
    problem = SimpleNamespace(
        source=ProblemSource.CODEFORCES,
        cf_contest_id=2254,
        cf_index="B",
        description="placeholder",
        sample_input=None,
        sample_output=None,
        time_limit_ms=1000,
        memory_limit_kb=262144,
        content_synced_at=None,
        content_sync_failed_at=None,
    )
    fetch = AsyncMock(return_value=parse_luogu_problem_page(_page({
        "content": {"description": "Statement", "formatI": "Input", "formatO": "Output"},
        "samples": [["abc", "2"]],
        "limits": {"time": [2000], "memory": [256000]},
    })))
    monkeypatch.setattr("app.services.codeforces.content.fetch_public_problem_content", fetch)

    assert await sync_problem_content(problem) is True
    assert problem.sample_input == "abc\n"
    assert problem.sample_output == "2\n"
    assert problem.content_synced_at is not None
    assert problem.content_sync_failed_at is None
