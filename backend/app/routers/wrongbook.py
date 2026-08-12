"""错题本 router (Task 12)。

API:
- GET  /wrongbook                  错题列表（分页，筛选 resolved/knowledge_id）
- GET  /wrongbook/{submission_id}  错题详情
- POST /wrongbook/{submission_id}/retry  标记重试
- GET  /wrongbook/{submission_id}/recommendations  同类题推荐

所有用户范围均由 JWT 当前用户解析，不接受外部 user_id。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
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

router = APIRouter(prefix="/wrongbook", tags=["wrongbook"])


@router.get("", response_model=WrongBookListResponse)
async def api_list_wrongbook(
    current_user: CurrentUser,
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
    return await list_wrongbook(db, current_user.id, params)


@router.get("/{submission_id}", response_model=WrongBookDetailResponse)
async def api_get_wrongbook_detail(
    submission_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WrongBookDetailResponse:
    result = await get_wrongbook_detail(db, submission_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="wrongbook entry not found")
    return result


@router.post("/{submission_id}/retry", response_model=RetryWrongBookResponse)
async def api_retry_wrongbook(
    submission_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> RetryWrongBookResponse:
    result = await retry_wrongbook(db, submission_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="wrongbook entry not found")
    return result


@router.get("/{submission_id}/recommendations", response_model=list[WrongBookRecommendation])
async def api_get_recommendations(
    submission_id: UUID,
    current_user: CurrentUser,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[WrongBookRecommendation]:
    return await get_recommendations(db, submission_id, current_user.id, limit)
