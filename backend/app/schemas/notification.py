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


# ===== Recommendation schemas (Task 12 智能推送引擎) =====


class RecommendationProblem(BaseSchema):
    """推荐题目项：薄弱知识点关联的未 AC 题目。"""

    problem_id: UUID
    title: str
    slug: str
    difficulty: str
    cf_rating: float | None
    tags: list[str] = Field(default_factory=list, description="题目 CF 标签")
    reasons: list[str] = Field(default_factory=list, description="推荐理由（错题重做/题型偏好/难度匹配等）")


class RecommendationItem(BaseSchema):
    """推荐项：薄弱知识点 + 推荐题目列表。"""

    knowledge_id: UUID
    knowledge_name: str
    mastery: int = Field(..., ge=0, le=100, description="当前掌握度百分比")
    problems: list[RecommendationProblem]
    review_due: bool = Field(default=False, description="该知识点是否已到艾宾浩斯复习期")
    next_review_at: datetime | None = Field(default=None, description="下次复习时间（复习到期时非空）")
    reasons: list[str] = Field(default_factory=list, description="知识点推荐理由（薄弱/复习到期）")


class RecommendationResponse(BaseSchema):
    """GET /api/v1/notifications/recommendations 响应。"""

    user_id: UUID
    items: list[RecommendationItem]
