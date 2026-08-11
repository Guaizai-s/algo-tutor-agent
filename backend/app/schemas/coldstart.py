"""水平测试与冷启动 Pydantic schemas (API 契约, Task 9)。"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ColdStartResultResponse(BaseSchema):
    """冷启动结果。"""

    user_id: UUID
    method: str = Field(..., description="codeforces | diagnostic")
    target_rating_min: int
    target_rating_max: int
    mastered_count: int
    weak_count: int
    next_available_count: int
    diagnostic_problems: list[UUID] = Field(default_factory=list)


class CalibrationResponse(BaseSchema):
    """起点定标结果。"""

    mastered_count: int
    weak_count: int
    next_available_count: int
    weak_knowledge_ids: list[UUID] = Field(default_factory=list)
    next_knowledge_ids: list[UUID] = Field(default_factory=list)
