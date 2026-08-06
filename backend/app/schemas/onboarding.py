"""用户最小冷启动 API 契约。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class DiagnosticProblemRead(BaseSchema):
    id: UUID
    title: str
    difficulty: str
    cf_rating: float | None = None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)


class ColdStartResponse(BaseSchema):
    completed: bool
    mode: Literal["not_started", "cf_history", "diagnostic_required", "diagnostic"]
    cf_handle: str | None = None
    current_rating: int | None = None
    submission_count: int = 0
    mapped_knowledge_points: int = 0
    learning_path_id: UUID | None = None
    diagnostic_problems: list[DiagnosticProblemRead] = Field(default_factory=list)
    message: str
    sync_error: str | None = None


class DiagnosticResult(BaseSchema):
    problem_id: UUID
    correct: bool


class DiagnosticSubmitRequest(BaseSchema):
    results: list[DiagnosticResult] = Field(min_length=1, max_length=15)
