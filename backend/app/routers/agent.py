"""Agent chat endpoints for JSON and Server-Sent Events responses."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from starlette.responses import StreamingResponse

from app.agents.tutor_agent import TutorAgent
from app.core.database import async_session_maker
from app.core.deps import CurrentUser
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_quota import AgentQuotaExceededError, consume_agent_quota
from app.services.openai_service import get_openai

if TYPE_CHECKING:
    from app.services.rag import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _answer_chunks(message: str, size: int = 24) -> list[str]:
    """Split a completed answer into small transport chunks for incremental rendering."""
    return [message[offset : offset + size] for offset in range(0, len(message), size)]


async def stream_agent_events(agent: TutorAgent, req: AgentChatRequest) -> AsyncIterator[str]:
    """Bridge Agent progress callbacks to an SSE stream.

    Trace steps are delivered while the Agent works. The final answer is sent in
    incremental chunks so clients can render it without waiting for a JSON body.
    """
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    task = asyncio.create_task(agent.run(req, on_event=on_event))
    try:
        while not task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            yield _sse(event)

        response = await task
        for chunk in _answer_chunks(response.message):
            yield _sse({"type": "answer_delta", "delta": chunk})
            await asyncio.sleep(0)
        yield _sse(
            {
                "type": "done",
                "references": [item.model_dump(mode="json") for item in response.references],
                "tool_calls": [item.model_dump(mode="json") for item in response.tool_calls],
                "trace": [item.model_dump(mode="json") for item in response.trace],
            }
        )
    except OpenAIError as exc:
        logger.warning("openai error during streamed agent run: %s", type(exc).__name__)
        yield _sse({"type": "error", "message": f"LLM 服务不可用: {type(exc).__name__}"})
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("streamed agent internal error")
        yield _sse({"type": "error", "message": "Agent 处理失败"})
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _get_rag() -> RAGService:
    from app.services.rag import rag_service

    if rag_service is None:  # pragma: no cover - lifespan guarantees it
        raise HTTPException(status_code=503, detail="RAG service not ready")
    return rag_service


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    req: AgentChatRequest,
    current_user: CurrentUser,
    openai=Depends(get_openai),
) -> AgentChatResponse:
    try:
        await consume_agent_quota(current_user.id)
    except AgentQuotaExceededError:
        raise HTTPException(status_code=429, detail="今日 AI Tutor 调用次数已用完") from None
    rag = _get_rag()
    agent = TutorAgent(openai, async_session_maker, rag, user_id=current_user.id)
    try:
        return await agent.run(req)
    except OpenAIError as exc:
        logger.warning("openai error during agent run: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"LLM 服务不可用: {type(exc).__name__}")
    except Exception:
        logger.exception("agent internal error")
        raise HTTPException(status_code=500, detail="Agent 处理失败")


@router.post("/chat/stream")
async def agent_chat_stream(
    req: AgentChatRequest,
    current_user: CurrentUser,
    openai=Depends(get_openai),
) -> StreamingResponse:
    """Stream safe Agent workflow summaries and the final answer over SSE."""
    try:
        await consume_agent_quota(current_user.id)
    except AgentQuotaExceededError:
        raise HTTPException(status_code=429, detail="今日 AI Tutor 调用次数已用完") from None

    agent = TutorAgent(openai, async_session_maker, _get_rag(), user_id=current_user.id)
    return StreamingResponse(
        stream_agent_events(agent, req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
