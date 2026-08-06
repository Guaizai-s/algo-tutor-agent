"""讨论区 router (Task 15)。

API:
- GET    /discussions              列表（分页、筛选）
- GET    /discussions/{id}         详情（含评论树）
- POST   /discussions              发帖
- PUT    /discussions/{id}         编辑
- DELETE /discussions/{id}         删帖
- POST   /discussions/{id}/like    点赞
- POST   /discussions/{id}/comments     评论
- DELETE /discussions/{id}/comments/{cid}  删评论

COMPAT: author_id 显式从查询参数/请求体传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.discussion import DiscussionCategory
from app.schemas.discussion import (
    DiscussionCommentCreate,
    DiscussionCommentRead,
    DiscussionCreate,
    DiscussionDetailResponse,
    DiscussionListParams,
    DiscussionListResponse,
    DiscussionRead,
    DiscussionUpdate,
)
from app.services.discussion import (
    create_comment,
    create_discussion,
    delete_comment,
    delete_discussion,
    get_discussion,
    like_discussion,
    list_discussions,
    update_discussion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discussions", tags=["discussions"])


@router.get("", response_model=DiscussionListResponse)
async def api_list_discussions(
    category: DiscussionCategory | None = Query(None),
    knowledge_id: UUID | None = Query(None),
    problem_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DiscussionListResponse:
    params = DiscussionListParams(
        category=category,
        knowledge_id=knowledge_id,
        problem_id=problem_id,
        page=page,
        page_size=page_size,
    )
    return await list_discussions(db, params)


@router.get("/{discussion_id}", response_model=DiscussionDetailResponse)
async def api_get_discussion(
    discussion_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DiscussionDetailResponse:
    result = await get_discussion(db, discussion_id)
    if result is None:
        raise HTTPException(status_code=404, detail="discussion not found")
    return result


@router.post("", response_model=DiscussionRead, status_code=201)
async def api_create_discussion(
    data: DiscussionCreate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> DiscussionRead:
    return await create_discussion(db, author_id, data)


@router.put("/{discussion_id}", response_model=DiscussionRead)
async def api_update_discussion(
    discussion_id: UUID,
    data: DiscussionUpdate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> DiscussionRead:
    result = await update_discussion(db, discussion_id, author_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="discussion not found or not authorized")
    return result


@router.delete("/{discussion_id}", status_code=204, response_class=Response)
async def api_delete_discussion(
    discussion_id: UUID,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_discussion(db, discussion_id, author_id)
    if not ok:
        raise HTTPException(status_code=404, detail="discussion not found or not authorized")


@router.post("/{discussion_id}/like", response_model=DiscussionRead)
async def api_like_discussion(
    discussion_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DiscussionRead:
    result = await like_discussion(db, discussion_id)
    if result is None:
        raise HTTPException(status_code=404, detail="discussion not found")
    return result


@router.post("/{discussion_id}/comments", response_model=DiscussionCommentRead, status_code=201)
async def api_create_comment(
    discussion_id: UUID,
    data: DiscussionCommentCreate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> DiscussionCommentRead:
    result = await create_comment(db, discussion_id, author_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="discussion not found or parent comment not found")
    return result


@router.delete("/{discussion_id}/comments/{comment_id}", status_code=204, response_class=Response)
async def api_delete_comment(
    discussion_id: UUID,
    comment_id: UUID,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_comment(db, comment_id, discussion_id, author_id)
    if not ok:
        raise HTTPException(status_code=404, detail="comment not found or not authorized")
