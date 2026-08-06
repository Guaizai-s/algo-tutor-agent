"""Agent router: POST /api/v1/agent/chat

First version returns a plain JSON response. SSE streaming is a TODO.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError

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
