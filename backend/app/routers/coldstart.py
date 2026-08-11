"""水平测试与冷启动 API (Task 9)。

API:
- POST /api/v1/coldstart/cf        CF 冷启动
- POST /api/v1/coldstart/diagnostic 诊断题冷启动
- GET  /api/v1/coldstart/calibration 起点定标

COMPAT: user_id 显式从查询参数/请求体传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.coldstart import CalibrationResponse, ColdStartResultResponse
from app.services.coldstart import (
    _calibrate_starting_point,
    cf_cold_start,
    diagnostic_cold_start,
)

router = APIRouter(prefix="/coldstart", tags=["coldstart"])


@router.post("/cf", response_model=ColdStartResultResponse)
async def api_cf_cold_start(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> ColdStartResultResponse:
    """CF 冷启动：拉取 CF 提交记录，映射知识点，计算 mastery。

    仅当用户在 CF 有 ≥ 20 条提交记录时走此路径。
    否则返回 suboptimal 结果（前端应提示用户走诊断题路径）。
    """
    result = await cf_cold_start(db, user_id)
    return ColdStartResultResponse(
        user_id=result.user_id,
        method=result.method,
        target_rating_min=result.target_rating_min,
        target_rating_max=result.target_rating_max,
        mastered_count=result.mastered_count,
        weak_count=result.weak_count,
        next_available_count=result.next_available_count,
        diagnostic_problems=result.diagnostic_problems,
    )


@router.post("/diagnostic", response_model=ColdStartResultResponse)
async def api_diagnostic_cold_start(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> ColdStartResultResponse:
    """诊断题冷启动：从自建题库选 15 题覆盖 10 核心知识点。

    选题规则：5 易 + 7 中 + 3 难。
    """
    result = await diagnostic_cold_start(db, user_id)
    return ColdStartResultResponse(
        user_id=result.user_id,
        method=result.method,
        target_rating_min=result.target_rating_min,
        target_rating_max=result.target_rating_max,
        mastered_count=result.mastered_count,
        weak_count=result.weak_count,
        next_available_count=result.next_available_count,
        diagnostic_problems=result.diagnostic_problems,
    )


@router.get("/calibration", response_model=CalibrationResponse)
async def api_calibrate_starting_point(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> CalibrationResponse:
    """起点定标：识别已掌握、薄弱、下一可学节点。"""
    result = await _calibrate_starting_point(db, user_id)
    return CalibrationResponse(
        mastered_count=result.mastered_count,
        weak_count=result.weak_count,
        next_available_count=result.next_available_count,
        weak_knowledge_ids=result.weak_knowledge_ids,
        next_knowledge_ids=result.next_knowledge_ids,
    )
