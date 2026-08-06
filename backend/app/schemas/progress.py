"""学习进度与掌握度 Pydantic schemas (API 契约, Task 11)。

字段对齐前端 frontend/src/types/index.ts 的 Progress 类型，
并补充 spec 要求的 rating_history 与 target_progress（COMPAT: 占位）。
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class MasteryByCategory(BaseModel):
    """雷达图单项：知识点 ID + 名称 + mastery 百分比（0-100）。

    knowledge_id 用于前端映射 weak_knowledge_ids。
    """

    knowledge_id: UUID
    name: str
    value: int = Field(..., ge=0, le=100, description="mastery 百分比，0-100")


class RatingHistoryPoint(BaseModel):
    """CF Rating 曲线单点。COMPAT: Task 8 CF 同步未实现前返回空列表。"""

    date: str
    rating: int


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
    wrong_answers: int = 0
    unresolved_wrong_answers: int = 0


class RecomputeMasteryRequest(BaseSchema):
    """POST /api/v1/progress/recompute 请求；用户身份来自 JWT。"""

    knowledge_id: UUID | None = Field(
        default=None,
        description="指定知识点 ID；None 时重算用户所有知识点 mastery",
    )


class RecomputeMasteryResponse(BaseSchema):
    """重算 mastery 响应。"""

    user_id: UUID
    recomputed: int = Field(..., description="本次重算的知识点数量")
    updated: int = Field(..., description="mastery 实际发生变化的知识点数量")
