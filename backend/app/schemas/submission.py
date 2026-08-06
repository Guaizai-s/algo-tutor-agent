"""提交记录查询 Pydantic Schema (API 契约, Role A 查询路由)。

只读查询，写入由 Role B 判题完成。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import BaseSchema, PageParams, PageResponse


class SubmissionRead(BaseSchema):
    """提交记录列表项。"""

    id: UUID
    cf_submission_id: int | None = None
    user_id: UUID
    problem_id: UUID | None
    problem_title: str | None = None
    contest_id: int | None = None
    problem_index: str | None = None
    verdict: str
    programming_language: str
    submitted_at: datetime
    time_consumed_ms: int
    memory_consumed_bytes: int
    passed_test_count: int


class SubmissionListParams(PageParams):
    problem_id: UUID | None = None
    verdict: str | None = None  # "OK", "WRONG_ANSWER", etc.


class SubmissionListResponse(PageResponse[SubmissionRead]):
    pass


class SubmissionDetailResponse(SubmissionRead):
    """提交详情（含题目信息）。"""

    problem_description: str | None = None
    problem_difficulty: str | None = None
    problem_cf_rating: float | None = None
