"""Learning path & daily task Pydantic schemas (API 契约, Task 10)。

注意：所有响应都使用 schema，不直接返回 ORM 对象或 dict。
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.learning import (
    DailyTaskItemStatus,
    DailyTaskItemType,
    PathItemKind,
    PathItemStatus,
)
from app.schemas.common import BaseSchema

# ===== 共享子结构 =====


class KnowledgePointRef(BaseSchema):
    """知识点精简引用。"""

    id: UUID
    name: str
    slug: str


class ProblemRef(BaseSchema):
    """题目精简引用。"""

    id: UUID
    title: str
    slug: str
    difficulty: str
    cf_rating: float | None = None


class LectureRef(BaseSchema):
    """讲义精简引用。"""

    id: UUID
    knowledge_id: UUID
    level: str
    title: str


# ===== 10.1 路径生成 =====


class LearningPathGenerateRequest(BaseSchema):
    """生成当前 JWT 用户的学习路径。"""

    preview_count: int = Field(default=8, ge=5, le=10)


class LearningPathItemRead(BaseSchema):
    id: UUID
    knowledge_id: UUID
    position: int
    kind: PathItemKind
    status: PathItemStatus
    knowledge: KnowledgePointRef


class LearningPathRead(BaseSchema):
    id: UUID
    user_id: UUID
    is_active: bool
    items: list[LearningPathItemRead]


# ===== 自评标记 =====


class MarkMasteredRequest(BaseSchema):
    """标记当前 JWT 用户的知识点为已掌握（自评）。"""

    knowledge_id: UUID


class MarkMasteredResponse(BaseSchema):
    """标记结果。"""

    knowledge_id: UUID
    mastery: float
    items_skipped: int = Field(default=0, description="路径中被标记为 skipped 的项数")


# ===== 10.2 路径动态调整 =====


class AttemptRequest(BaseSchema):
    """记录当前 JWT 用户的一次做题结果（用于驱动路径动态调整）。

    注意：mastery 由服务端按 spec 计算（AC 题数 / 关联题目总数），
    客户端不得通过 new_mastery 覆盖。该字段保留仅为向后兼容，
    服务端会忽略它（deprecated）。
    """

    knowledge_id: UUID
    problem_id: UUID
    verdict: str = Field(..., description="AC / WA / TLE / RE 等")
    # DEPRECATED: 客户端传入的 new_mastery 会被服务端忽略。
    # mastery 始终由服务端按 spec 计算（AC/总数）。
    new_mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="[DEPRECATED] 服务端忽略此字段，mastery 由服务端按 spec 计算",
    )


class AttemptResponse(BaseSchema):
    user_id: UUID
    knowledge_id: UUID
    consecutive_wa: int
    is_weak: bool
    mastery: float
    remediation_inserted: bool = Field(..., description="本次是否在路径中插入或提升了一个补漏任务")


# ===== 10.3 当日任务 =====


class DailyTaskItemRead(BaseSchema):
    id: UUID
    item_type: DailyTaskItemType
    position: int
    lecture: LectureRef | None = None
    problem: ProblemRef | None = None
    status: DailyTaskItemStatus
    missing_reason: str | None = None


class DailyTaskRead(BaseSchema):
    id: UUID
    user_id: UUID
    task_date: date
    knowledge: KnowledgePointRef
    is_remediation: bool
    missing_slots: list[str]
    items: list[DailyTaskItemRead]


class DailyTaskPathPreviewItem(BaseModel):
    """路径预览项（当日任务接口附带）。"""

    knowledge_id: UUID
    name: str
    position: int
    kind: PathItemKind


class DailyTaskTodayResponse(BaseSchema):
    """当日任务 + 路径预览聚合响应。"""

    task: DailyTaskRead
    path_preview: list[DailyTaskPathPreviewItem]


class DailyTaskItemUpdateRequest(BaseSchema):
    """更新任务项状态（标记完成/跳过）。"""

    status: DailyTaskItemStatus = Field(..., description="目标状态：done / skipped")


class DailyTaskItemUpdateResponse(BaseSchema):
    """任务项状态更新响应。"""

    item: DailyTaskItemRead
    task_done: int = Field(0, description="当前任务已完成项数")
    task_total: int = Field(0, description="当前任务总项数")
    all_done: bool = Field(False, description="是否全部完成")
    check_in: bool = Field(False, description="本次是否触发了打卡")
    auto_mastered: bool = Field(False, description="是否自动标记知识点为已掌握")


# ===== Roadmap view (路线图视图) =====


class RoadmapKnowledgeNode(BaseSchema):
    """路线图知识点节点：知识树 + 用户学习状态聚合。"""

    id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    difficulty: str
    order: int
    lecture_count: int
    template_count: int
    # 学习状态
    status: str = Field(..., description="done | active | pending | unlocked | none")
    mastery: float | None = None
    is_weak: bool = False
    path_position: int | None = None
    # 双维度进度：理论（讲义阅读）+ 实践（题目 AC）
    theory_done: bool = Field(False, description="讲义已读（理论知识验收）")
    practice_mastery: float | None = Field(None, description="实践 mastery（AC 题数/关联题总数）")
    theory_lecture_count: int = Field(0, description="该知识点已读讲义数（分母为 lecture_count）")
    # 双维度难度评价（1-5 数值）
    comprehension_difficulty: int = 1
    theory_depth: int = 1


class RoadmapResponse(BaseSchema):
    """路线图聚合响应。"""

    user_id: UUID
    has_path: bool
    tree: list[RoadmapKnowledgeNode]
    path_preview: list[KnowledgePointRef]


# ===== internal helpers (not exposed as API) =====


class _MissingSlots(BaseModel):
    """内部用：缺失槽位收集。"""

    slots: list[str] = Field(default_factory=list)
