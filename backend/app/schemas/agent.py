"""Agent API 契约 (Pydantic v2)。

客户端不可伪造 system 消息；history 仅允许 user/assistant。
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    # 故意不含 system —— 客户端不得伪造


class ChatHistoryItem(BaseModel):
    role: ChatRole
    content: str = Field(..., max_length=4000)


class AgentContext(BaseModel):
    problem_id: UUID | None = None
    language: Literal["python", "cpp", "java"] | None = None
    code: str | None = Field(None, max_length=20000)


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=20)
    context: AgentContext | None = None


class AgentReference(BaseModel):
    type: Literal["problem", "knowledge"]
    id: UUID
    title: str
    source: str


class AgentToolCallSummary(BaseModel):
    # name uses a plain string (not Literal) so that unknown tool names
    # requested by the model are surfaced as "error" status rather than
    # triggering a Pydantic ValidationError -> 500.
    name: str
    status: Literal["success", "error"]


class AgentTraceStep(BaseModel):
    """A user-facing, non-sensitive summary of one Agent workflow step."""

    id: str
    kind: Literal["understanding", "planning", "tool", "answer"]
    title: str
    detail: str | None = None
    status: Literal["running", "success", "error"]
    tool_name: str | None = None


class AgentChatResponse(BaseModel):
    message: str
    references: list[AgentReference] = Field(default_factory=list)
    tool_calls: list[AgentToolCallSummary] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
