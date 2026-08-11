"""在线判题 API (Task 8 判题系统)。

API:
- POST /api/v1/judge/run  提交代码并判题

COMPAT: user_id 显式从请求体传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.judge import judge

router = APIRouter(prefix="/judge", tags=["judge"])


class JudgeRequest(BaseModel):
    """判题请求。"""

    user_id: UUID = Field(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）")
    problem_id: UUID | None = Field(None, description="题目 ID（可选）")
    source_code: str = Field(..., min_length=1, max_length=65536, description="源代码")
    language: str = Field(..., description="语言: cpp | python | java")
    test_input: str = Field(default="", description="测试输入")
    expected_output: str = Field(default="", description="预期输出")
    timeout_ms: int = Field(default=3000, ge=500, le=5000, description="时间限制(ms)")
    memory_mb: int = Field(default=256, ge=32, le=512, description="内存限制(MB)")


class JudgeResponse(BaseModel):
    """判题响应。"""

    verdict: str
    time_ms: int = 0
    memory_kb: int = 0
    stdout: str = ""
    stderr: str = ""
    message: str = ""


@router.post("/run", response_model=JudgeResponse)
async def api_judge(
    req: JudgeRequest,
    db: AsyncSession = Depends(get_db),
) -> JudgeResponse:
    """提交代码并判题。

    在 Docker 沙箱中执行代码，对比输出与预期答案。
    """
    result = await judge(
        source_code=req.source_code,
        language=req.language,
        test_input=req.test_input,
        expected_output=req.expected_output,
        timeout_ms=req.timeout_ms,
        memory_mb=req.memory_mb,
    )
    return JudgeResponse(
        verdict=result.verdict.value,
        time_ms=result.time_ms,
        memory_kb=result.memory_kb,
        stdout=result.stdout,
        stderr=result.stderr,
        message=result.message,
    )
