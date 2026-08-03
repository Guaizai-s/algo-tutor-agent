"""Problem 相关 Pydantic Schema (API 契约)。

注意：严禁在公开 Read Schema 中暴露 test_cases 字段。
"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.problem import ProblemDifficulty, ProblemStatus
from app.schemas.common import BaseSchema, PageResponse, TimestampSchema


class ProblemBase(BaseSchema):
    title: str = Field(..., max_length=300)
    slug: str = Field(..., max_length=300)
    description: str
    difficulty: ProblemDifficulty
    time_limit_ms: int = 1000
    memory_limit_kb: int = 262144
    sample_input: str | None = None
    sample_output: str | None = None
    hints: list[str] | None = None
    solution_template: dict | None = None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)


class ProblemRead(TimestampSchema, ProblemBase):
    """公开读取 Schema，显式排除 test_cases。"""

    status: ProblemStatus
    submit_count: int
    accepted_count: int
    cf_rating: float | None = None


class ProblemListResponse(PageResponse[ProblemRead]):
    pass


class CodeExecutionRequest(BaseSchema):
    """直接运行代码的请求；不经过 LLM/Agent。"""

    language: Literal["python", "cpp", "java"]
    code: str = Field(..., min_length=1, max_length=50000)


class CodeExecutionResponse(BaseSchema):
    """沙箱的真实执行结果。"""

    status: Literal["success", "compile_error", "runtime_error", "timeout", "internal_error"]
    stdout: str
    stderr: str
    exit_code: int
    time_used_ms: int
    truncated: bool
    input_source: Literal["sample", "empty"]
    message: str
