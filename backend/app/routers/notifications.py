"""通知推送 router (Task 12 智能推送引擎)。

API:
- GET  /notifications          通知列表（分页）
- POST /notifications/{id}/read  标记已读
- POST /notifications/read-all   全部已读

COMPAT: user_id 显式从查询参数传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.notification import NotificationListResponse, NotificationRead
from app.services.push import get_notifications, mark_all_read, mark_read

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def api_list_notifications(
    current_user: CurrentUser,
    unread_only: bool = Query(False, description="仅返回未读通知"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
):
    """获取通知列表（分页）。"""
    items, total, unread_count = await get_notifications(
        db,
        current_user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[
            NotificationRead(
                id=n.id,
                user_id=n.user_id,
                notification_type=n.notification_type,
                title=n.title,
                body=n.body,
                is_read=n.is_read,
                read_at=n.read_at,
                related_knowledge_id=n.related_knowledge_id,
                related_problem_id=n.related_problem_id,
                created_at=n.created_at,
            )
            for n in items
        ],
        total=total,
        unread_count=unread_count,
    )


@router.post("/{notification_id}/read")
async def api_mark_read(
    notification_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """标记通知已读。"""
    notification = await mark_read(db, notification_id, current_user.id)
    if notification is None:
        raise HTTPException(status_code=404, detail="通知不存在或不属于该用户")
    return {"id": str(notification.id), "read": True}


@router.post("/read-all")
async def api_mark_all_read(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """全部标记已读。"""
    count = await mark_all_read(db, current_user.id)
    return {"message": f"{count} notifications marked as read", "count": count}
