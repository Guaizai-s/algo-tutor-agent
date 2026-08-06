"""Learning router: Task 10 学习路径与推送引擎。

API:
- POST /api/v1/learning-paths/generate
- GET  /api/v1/learning-paths/current
- POST /api/v1/learning-paths/attempts
- GET  /api/v1/daily-tasks/today

所有用户范围均由 JWT 当前用户解析，不接受外部 user_id。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.learning import (
    AttemptRequest,
    AttemptResponse,
    DailyTaskTodayResponse,
    LearningPathGenerateRequest,
    LearningPathRead,
)
from app.services.daily_tasks import get_or_create_today_task
from app.services.learning_path import (
    CycleDetectedError,
    generate_learning_path,
    get_current_learning_path,
    record_attempt,
)

logger = logging.getLogger(__name__)

# 学习路径相关 API
path_router = APIRouter(prefix="/learning-paths", tags=["learning-path"])
# 当日任务相关 API
daily_router = APIRouter(prefix="/daily-tasks", tags=["daily-task"])


@path_router.post("/generate", response_model=LearningPathRead)
async def api_generate_learning_path(
    req: LearningPathGenerateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> LearningPathRead:
    """生成（或重新生成）用户学习路径。"""
    try:
        result = await generate_learning_path(db, current_user.id, req.preview_count)
    except CycleDetectedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cycle_detected",
                "message": "知识点前置依赖图中存在环，无法生成路径",
                "cycle_nodes": [str(n) for n in exc.cycle_nodes],
            },
        )
    return result


@path_router.get("/current", response_model=LearningPathRead)
async def api_get_current_learning_path(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> LearningPathRead:
    """获取用户当前 active 学习路径。"""
    result = await get_current_learning_path(db, current_user.id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="用户尚未生成学习路径，请先调用 POST /api/v1/learning-paths/generate",
        )
    return result


@path_router.post("/attempts", response_model=AttemptResponse)
async def api_record_attempt(
    req: AttemptRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> AttemptResponse:
    """记录一次做题结果，触发路径动态调整。"""
    return await record_attempt(
        db,
        user_id=current_user.id,
        knowledge_id=req.knowledge_id,
        problem_id=req.problem_id,
        verdict=req.verdict,
        new_mastery=req.new_mastery,
    )


@daily_router.get("/today", response_model=DailyTaskTodayResponse)
async def api_get_today_task(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> DailyTaskTodayResponse:
    """获取今日任务（幂等：同日重复请求返回同一份计划）。"""
    try:
        return await get_or_create_today_task(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
