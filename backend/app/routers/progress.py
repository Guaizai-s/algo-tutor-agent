"""Progress router: Task 11 学习进度与掌握度。

API:
- GET  /api/v1/progress/overview   聚合进度面板数据
- POST /api/v1/progress/recompute  重算 mastery（手动触发）

COMPAT: user_id 显式从查询参数/请求体传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.progress import (
    ActivityResponse,
    CheckInResponse,
    ProgressOverviewResponse,
    RecomputeMasteryRequest,
    RecomputeMasteryResponse,
)
from app.services.progress import (
    do_check_in,
    get_activity,
    get_check_in_status,
    get_progress_overview,
    recompute_mastery,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/overview", response_model=ProgressOverviewResponse)
async def api_get_progress_overview(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> ProgressOverviewResponse:
    """获取用户进度面板聚合数据。"""
    return await get_progress_overview(db, user_id)


@router.post("/recompute", response_model=RecomputeMasteryResponse)
async def api_recompute_mastery(
    req: RecomputeMasteryRequest,
    db: AsyncSession = Depends(get_db),
) -> RecomputeMasteryResponse:
    """手动重算 mastery（管理后台或调试用）。

    业务流程中 AC 时会自动重算，一般无需手动调用。
    若指定 knowledge_id 不存在，返回 404。
    """
    try:
        return await recompute_mastery(db, req.user_id, req.knowledge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/checkin", response_model=CheckInResponse)
async def api_check_in(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> CheckInResponse:
    """每日打卡。幂等：多次调用同一天只记录一次。"""
    return await do_check_in(db, user_id)


@router.get("/checkin", response_model=CheckInResponse)
async def api_get_check_in_status(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> CheckInResponse:
    """查询今日打卡状态。"""
    return await get_check_in_status(db, user_id)


@router.get("/wrong-answers")
async def api_get_wrong_answers(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取错题列表（前端兼容路径，转发到 wrongbook 服务）。"""
    from app.schemas.wrongbook import WrongBookListParams
    from app.services.wrongbook import list_wrongbook

    params = WrongBookListParams(page=page, page_size=page_size)
    return await list_wrongbook(db, user_id, params)


@router.get("/activity", response_model=ActivityResponse)
async def api_get_activity(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    days: int = Query(30, ge=1, le=90, description="查询天数，默认 30"),
    db: AsyncSession = Depends(get_db),
) -> ActivityResponse:
    """获取近 N 天每日提交活动数据。"""
    return await get_activity(db, user_id, days)
