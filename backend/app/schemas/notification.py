"""通知推送 Pydantic schemas (API 契约, Task 12 智能推送引擎)。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.notification import NotificationType
from app.schemas.common import BaseSchema


class NotificationRead(BaseSchema):
    """通知响应。"""

    id: UUID
    user_id: UUID
    notification_type: NotificationType
    title: str
    body: str
    is_read: bool
    read_at: datetime | None = None
    related_knowledge_id: UUID | None = None
    related_problem_id: UUID | None = None
    created_at: datetime


class NotificationListResponse(BaseSchema):
    """通知列表响应。"""

    items: list[NotificationRead]
    total: int
    unread_count: int


class NotificationCreateRequest(BaseSchema):
    """创建通知请求（内部 service 使用，不暴露为 API）。"""

    user_id: UUID
    notification_type: NotificationType
    title: str = Field(..., max_length=255)
    body: str
    related_knowledge_id: UUID | None = None
    related_problem_id: UUID | None = None


# ===== Recommendation schemas (Task 12 智能推送引擎) =====


class RecommendationProblem(BaseSchema):
    """推荐题目项：薄弱知识点关联的未 AC 题目。"""

    problem_id: UUID
    title: str
    slug: str
    difficulty: str
    cf_rating: float | None


class RecommendationItem(BaseSchema):
    """推荐项：薄弱知识点 + 推荐题目列表。"""

    knowledge_id: UUID
    knowledge_name: str
    mastery: int = Field(..., ge=0, le=100, description="当前掌握度百分比")
    problems: list[RecommendationProblem]


class RecommendationResponse(BaseSchema):
    """GET /api/v1/notifications/recommendations 响应。"""

    user_id: UUID
    items: list[RecommendationItem]
