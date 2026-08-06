"""Progress router: Task 11 学习进度与掌握度。

API:
- GET  /api/v1/progress/overview   聚合进度面板数据
- POST /api/v1/progress/recompute  重算 mastery（手动触发）

所有用户范围均由 JWT 当前用户解析，不接受外部 user_id。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.progress import (
    ProgressOverviewResponse,
    RecomputeMasteryRequest,
    RecomputeMasteryResponse,
)
from app.services.progress import get_progress_overview, recompute_mastery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/overview", response_model=ProgressOverviewResponse)
async def api_get_progress_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ProgressOverviewResponse:
    """获取用户进度面板聚合数据。"""
    return await get_progress_overview(db, current_user.id)


@router.post("/recompute", response_model=RecomputeMasteryResponse)
async def api_recompute_mastery(
    req: RecomputeMasteryRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> RecomputeMasteryResponse:
    """手动重算 mastery（管理后台或调试用）。

    业务流程中 AC 时会自动重算，一般无需手动调用。
    若指定 knowledge_id 不存在，返回 404。
    """
    try:
        return await recompute_mastery(db, current_user.id, req.knowledge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
