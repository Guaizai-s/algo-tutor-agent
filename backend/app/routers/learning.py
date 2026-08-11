"""Learning router: Task 10 学习路径与推送引擎。

API:
- POST /api/v1/learning-paths/generate
- GET  /api/v1/learning-paths/current
- POST /api/v1/learning-paths/attempts
- GET  /api/v1/daily-tasks/today

COMPAT: user_id 显式从请求体/查询参数传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.learning import (
    AttemptRequest,
    AttemptResponse,
    DailyTaskItemUpdateRequest,
    DailyTaskItemUpdateResponse,
    DailyTaskTodayResponse,
    LearningPathGenerateRequest,
    LearningPathRead,
    MarkMasteredRequest,
    MarkMasteredResponse,
    RoadmapResponse,
)
from app.services.daily_tasks import get_or_create_today_task, update_daily_task_item
from app.services.learning_path import (
    CycleDetectedError,
    generate_learning_path,
    get_current_learning_path,
    get_roadmap_data,
    mark_knowledge_mastered,
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
    db: AsyncSession = Depends(get_db),
) -> LearningPathRead:
    """生成（或重新生成）用户学习路径。"""
    try:
        result = await generate_learning_path(db, req.user_id, req.preview_count)
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


@path_router.post("/mark-mastered", response_model=MarkMasteredResponse)
async def api_mark_mastered(
    req: MarkMasteredRequest,
    db: AsyncSession = Depends(get_db),
) -> MarkMasteredResponse:
    """标记知识点为已掌握（自评），跳过路径中对应项。"""
    mastery, skipped = await mark_knowledge_mastered(db, req.user_id, req.knowledge_id)
    return MarkMasteredResponse(
        knowledge_id=req.knowledge_id,
        mastery=mastery,
        items_skipped=skipped,
    )


@path_router.get("/current", response_model=LearningPathRead)
async def api_get_current_learning_path(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> LearningPathRead:
    """获取用户当前 active 学习路径。"""
    result = await get_current_learning_path(db, user_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="用户尚未生成学习路径，请先调用 POST /api/v1/learning-paths/generate",
        )
    return result


@path_router.get("/roadmap", response_model=RoadmapResponse)
async def api_get_roadmap(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> RoadmapResponse:
    """获取路线图聚合数据：知识树 + 用户学习状态。"""
    return await get_roadmap_data(db, user_id)


@path_router.post("/attempts", response_model=AttemptResponse)
async def api_record_attempt(
    req: AttemptRequest,
    db: AsyncSession = Depends(get_db),
) -> AttemptResponse:
    """记录一次做题结果，触发路径动态调整。"""
    return await record_attempt(
        db,
        user_id=req.user_id,
        knowledge_id=req.knowledge_id,
        problem_id=req.problem_id,
        verdict=req.verdict,
        new_mastery=req.new_mastery,
    )


@daily_router.get("/today", response_model=DailyTaskTodayResponse)
async def api_get_today_task(
    user_id: UUID = Query(..., description="用户 ID（COMPAT: 认证落地后从 token 解析）"),
    db: AsyncSession = Depends(get_db),
) -> DailyTaskTodayResponse:
    """获取今日任务（幂等：同日重复请求返回同一份计划）。"""
    try:
        return await get_or_create_today_task(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@daily_router.patch("/{task_id}/items/{item_id}", response_model=DailyTaskItemUpdateResponse)
async def api_update_daily_task_item(
    task_id: UUID,
    item_id: UUID,
    req: DailyTaskItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> DailyTaskItemUpdateResponse:
    """更新任务项状态（标记完成/跳过），全部完成时自动打卡。"""
    try:
        return await update_daily_task_item(db, task_id, item_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
