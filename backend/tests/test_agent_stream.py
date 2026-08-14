"""SSE transport tests for the Tutor Agent."""

from __future__ import annotations

import json

import pytest

from app.routers.agent import stream_agent_events
from app.schemas.agent import AgentChatRequest, AgentChatResponse, AgentTraceStep


class _FakeAgent:
    async def run(self, request, on_event=None):  # type: ignore[no-untyped-def]
        assert request.message == "解释二分查找"
        trace = [
            AgentTraceStep(
                id="understanding",
                kind="understanding",
                title="理解学习目标",
                status="success",
            ),
            AgentTraceStep(
                id="answer",
                kind="answer",
                title="生成学习反馈",
                status="success",
            ),
        ]
        if on_event is not None:
            for step in trace:
                await on_event({"type": "trace", "step": step.model_dump(mode="json")})
        return AgentChatResponse(message="二分查找每次排除一半搜索区间。", trace=trace)


@pytest.mark.asyncio
async def test_stream_agent_events_emits_trace_answer_and_done():
    raw_events = [
        item
        async for item in stream_agent_events(
            _FakeAgent(),  # type: ignore[arg-type]
            AgentChatRequest(message="解释二分查找"),
        )
    ]
    events = [json.loads(item.removeprefix("data: ").strip()) for item in raw_events]

    assert [item["type"] for item in events[:2]] == ["trace", "trace"]
    assert "".join(item["delta"] for item in events if item["type"] == "answer_delta") == (
        "二分查找每次排除一半搜索区间。"
    )
    assert events[-1]["type"] == "done"
    assert len(events[-1]["trace"]) == 2
