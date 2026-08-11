"""艾宾浩斯复习 API (Task 13)。

API:
- POST /api/v1/review/start       创建复习记录（首次学习）
- POST /api/v1/review/complete    完成一次复习（推进阶段）
- GET  /api/v1/review/due         获取到期待复习项
- GET  /api/v1/review/status      获取复习状态概览
- GET  /api/v1/review/problem     获取复习推荐题目

COMPAT: user_id 显式从查询参数传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.services.review import (
    complete_review,
    create_review_record,
    get_due_reviews,
    get_review_problem,
    get_review_status,
)

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/start")
async def api_start_review(
    current_user: CurrentUser,
    knowledge_id: UUID = Query(..., description="知识点 ID"),
    db: AsyncSession = Depends(get_db),
):
    """创建复习记录（首次学习时调用）。幂等。"""
    record = await create_review_record(db, current_user.id, knowledge_id)
    return {
        "id": str(record.id),
        "knowledge_id": str(record.knowledge_id),
        "stage": record.stage.value,
        "next_review_at": record.next_review_at.isoformat() if record.next_review_at else None,
    }


@router.post("/complete")
async def api_complete_review(
    current_user: CurrentUser,
    knowledge_id: UUID = Query(..., description="知识点 ID"),
    db: AsyncSession = Depends(get_db),
):
    """完成一次复习：推进到下一阶段。"""
    try:
        record = await complete_review(db, current_user.id, knowledge_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": str(record.id),
        "knowledge_id": str(record.knowledge_id),
        "stage": record.stage.value,
        "next_review_at": record.next_review_at.isoformat() if record.next_review_at else None,
        "review_count": record.review_count,
    }


@router.get("/list")
async def api_get_review_list(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """获取复习列表（前端兼容接口，与 /due 行为一致）。"""
    records = await get_due_reviews(db, current_user.id)
    return [
        {
            "id": str(r.id),
            "knowledge_id": str(r.knowledge_id),
            "stage": r.stage.value,
            "next_review_at": r.next_review_at.isoformat() if r.next_review_at else None,
        }
        for r in records
    ]


@router.get("/due")
async def api_get_due_reviews(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """获取到期待复习项。"""
    records = await get_due_reviews(db, current_user.id)
    return [
        {
            "id": str(r.id),
            "knowledge_id": str(r.knowledge_id),
            "stage": r.stage.value,
            "next_review_at": r.next_review_at.isoformat() if r.next_review_at else None,
        }
        for r in records
    ]


@router.get("/status")
async def api_get_review_status(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """获取复习状态概览。"""
    return await get_review_status(db, current_user.id)


@router.get("/problem")
async def api_get_review_problem(
    current_user: CurrentUser,
    knowledge_id: UUID = Query(..., description="知识点 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取复习推荐题目（排除已 AC 题）。"""
    problem_id = await get_review_problem(db, knowledge_id, current_user.id)
    return {"problem_id": str(problem_id) if problem_id else None}
