"""学习进度与掌握度 Pydantic schemas (API 契约, Task 11)。

字段对齐前端 frontend/src/types/index.ts 的 Progress 类型，
并补充 spec 要求的 rating_history 与 target_progress（COMPAT: 占位）。
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class MasteryByCategory(BaseModel):
    """知识点掌握度单项：ID + 名称 + 父分类名 + mastery 百分比（0-100）。

    knowledge_id 用于前端映射 weak_knowledge_ids。
    parent_name 用于前端按一级分类分组展示（替代雷达图）。
    """

    knowledge_id: UUID
    name: str
    parent_name: str | None = Field(default=None, description="一级父分类名称，用于分组展示")
    value: int = Field(..., ge=0, le=100, description="mastery 百分比，0-100")


class RatingHistoryPoint(BaseModel):
    """CF Rating 曲线单点。COMPAT: Task 8 CF 同步未实现前返回空列表。"""

    date: str
    rating: int


class ReviewStatus(BaseModel):
    """艾宾浩斯复习状态概览。"""

    due_count: int = Field(0, description="到期待复习的知识点数")
    total_records: int = Field(0, description="总复习记录数")
    completed: int = Field(0, description="已完成复习数")


class TargetProgress(BaseModel):
    """训练目标完成进度。"""

    target_rating_min: int
    target_rating_max: int
    mastered_in_range: int = Field(..., description="训练目标 rating 区间内已掌握知识点数")
    total_in_range: int = Field(..., description="训练目标 rating 区间内知识点总数")
    progress_percent: int = Field(..., ge=0, le=100, description="完成百分比 0-100")


class ProgressOverviewResponse(BaseSchema):
    """GET /api/v1/progress/overview 响应。

    COMPAT: user_id 显式传入，等认证落地后改为从 token 解析。
    """

    user_id: UUID
    total_knowledge_points: int
    mastered_knowledge_points: int
    total_problems: int
    solved_problems: int
    acceptance_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="通过率，0-1 浮点数。前端展示时需乘以 100（如 0.5 → 50.0%）",
    )
    streak_days: int = Field(0, description="连续打卡天数。COMPAT: 无 submission 表前返回 0")
    mastery_by_category: list[MasteryByCategory]
    rating_history: list[RatingHistoryPoint] = Field(
        default_factory=list,
        description="CF Rating 曲线。COMPAT: Task 8 CF 同步未实现，始终返回空列表",
    )
    target_progress: TargetProgress | None = None
    weak_knowledge_ids: list[UUID] = Field(
        default_factory=list,
        description="薄弱知识点 ID（0 < mastery < 0.5；mastery=0 未学不算薄弱）",
    )
    review_status: ReviewStatus | None = Field(
        default=None,
        description="艾宾浩斯复习状态概览（无复习记录时为 None）",
    )


class RecomputeMasteryRequest(BaseSchema):
    """POST /api/v1/progress/recompute 请求。"""

    knowledge_id: UUID | None = Field(
        default=None,
        description="指定知识点 ID；None 时重算用户所有知识点 mastery",
    )


class RecomputeMasteryResponse(BaseSchema):
    """重算 mastery 响应。"""

    user_id: UUID
    recomputed: int = Field(..., description="本次重算的知识点数量")
    updated: int = Field(..., description="mastery 实际发生变化的知识点数量")


class CheckInResponse(BaseSchema):
    """打卡响应。"""

    user_id: UUID
    check_date: str
    streak_days: int
    is_today_checked: bool


class ActivityDay(BaseModel):
    """单日活动数据。"""

    date: str
    count: int = Field(0, description="当日提交数")


class ActivityResponse(BaseSchema):
    """GET /api/v1/progress/activity 响应。"""

    user_id: UUID
    days: list[ActivityDay]
    total_week: int = Field(0, description="本周总提交数")
    total_last_week: int = Field(0, description="上周总提交数")
