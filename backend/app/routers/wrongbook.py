"""错题本 router (Task 12)。

API:
- GET  /wrongbook                  错题列表（分页，筛选 resolved/knowledge_id）
- GET  /wrongbook/{submission_id}  错题详情
- POST /wrongbook/{submission_id}/retry  标记重试
- GET  /wrongbook/{submission_id}/recommendations  同类题推荐

COMPAT: user_id 显式从查询参数传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.wrongbook import (
    RetryWrongBookResponse,
    WrongBookDetailResponse,
    WrongBookListParams,
    WrongBookListResponse,
    WrongBookRecommendation,
)
from app.services.wrongbook import (
    get_recommendations,
    get_wrongbook_detail,
    list_wrongbook,
    retry_wrongbook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wrongbook", tags=["wrongbook"])


@router.get("", response_model=WrongBookListResponse)
async def api_list_wrongbook(
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    resolved: bool | None = Query(None),
    knowledge_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> WrongBookListResponse:
    params = WrongBookListParams(
        resolved=resolved,
        knowledge_id=knowledge_id,
        page=page,
        page_size=page_size,
    )
    return await list_wrongbook(db, user_id, params)


@router.get("/{submission_id}", response_model=WrongBookDetailResponse)
async def api_get_wrongbook_detail(
    submission_id: UUID,
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> WrongBookDetailResponse:
    result = await get_wrongbook_detail(db, submission_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="wrongbook entry not found")
    return result


@router.post("/{submission_id}/retry", response_model=RetryWrongBookResponse)
async def api_retry_wrongbook(
    submission_id: UUID,
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> RetryWrongBookResponse:
    result = await retry_wrongbook(db, submission_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="wrongbook entry not found")
    return result


@router.get("/{submission_id}/recommendations", response_model=list[WrongBookRecommendation])
async def api_get_recommendations(
    submission_id: UUID,
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[WrongBookRecommendation]:
    return await get_recommendations(db, submission_id, user_id, limit)
