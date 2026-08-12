"""题目推荐路由 (Task 12 智能推送引擎)。

API:
- GET  /api/v1/recommendations          基于薄弱知识点推荐未 AC 的题目
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.notification import RecommendationResponse
from app.services.push import get_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationResponse)
async def api_get_recommendations(
    current_user: CurrentUser,
    max_per_knowledge: int = Query(3, ge=1, le=10, description="每个知识点最多推荐题目数"),
    max_knowledge_points: int = Query(5, ge=1, le=10, description="最多推荐知识点数"),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """基于薄弱知识点推荐未 AC 的题目。

    按薄弱程度排序，每个知识点最多返回 max_per_knowledge 题（简单优先）。
    """
    return await get_recommendations(db, current_user.id, max_per_knowledge, max_knowledge_points)
