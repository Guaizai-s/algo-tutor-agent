"""错题本 Pydantic Schema (API 契约, Task 12)。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, PageParams, PageResponse


class WrongBookItem(BaseSchema):
    """错题本列表项。"""

    submission_id: UUID
    problem_id: UUID | None
    problem_title: str | None = None
    cf_contest_id: int | None = None
    cf_index: str | None = None
    verdict: str
    knowledge_point_names: list[str] = Field(default_factory=list)
    retry_count: int = 0
    resolved: bool = False
    submitted_at: datetime
    last_retry_at: datetime | None = None


class WrongBookListParams(PageParams):
    resolved: bool | None = None  # None=全部, True=已解决, False=未解决
    knowledge_id: UUID | None = None


class WrongBookListResponse(PageResponse[WrongBookItem]):
    pass


class WrongBookDetailResponse(WrongBookItem):
    """错题本详情（含题目信息）。"""

    problem_description: str | None = None
    problem_difficulty: str | None = None
    problem_cf_rating: float | None = None
    programming_language: str | None = None
    time_consumed_ms: int | None = None
    memory_consumed_bytes: int | None = None


class RetryWrongBookResponse(BaseSchema):
    submission_id: UUID
    retry_count: int
    resolved: bool


class WrongBookRecommendation(BaseSchema):
    """同类题推荐。"""

    problem_id: UUID
    title: str
    difficulty: str
    cf_rating: float | None
    knowledge_point_names: list[str] = Field(default_factory=list)
    ac_count: int = 0
    submit_count: int = 0
