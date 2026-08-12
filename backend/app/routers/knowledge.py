"""Knowledge router.

Lists knowledge points and their lectures. Read-only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.knowledge import (
    CodeTemplate,
    KnowledgePoint,
    KnowledgePrerequisite,
    Lecture,
)
from app.schemas.knowledge import (
    CodeTemplateRead,
    KnowledgePointRead,
    LectureRead,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def _enrich_kp_rows(db: AsyncSession, rows: list[KnowledgePoint]) -> list[KnowledgePointRead]:
    """为 KnowledgePoint 行附加 lecture_count / template_count / children_count。"""
    if not rows:
        return []
    ids = [kp.id for kp in rows]

    # 一次性聚合所有子统计
    lec_stats = (
        await db.execute(
            select(Lecture.knowledge_id, func.count(Lecture.id))
            .where(Lecture.knowledge_id.in_(ids))
            .group_by(Lecture.knowledge_id)
        )
    ).all()
    tpl_stats = (
        await db.execute(
            select(CodeTemplate.knowledge_id, func.count(CodeTemplate.id))
            .where(CodeTemplate.knowledge_id.in_(ids))
            .group_by(CodeTemplate.knowledge_id)
        )
    ).all()
    child_stats = (
        await db.execute(
            select(KnowledgePoint.parent_id, func.count(KnowledgePoint.id))
            .where(KnowledgePoint.parent_id.in_(ids))
            .group_by(KnowledgePoint.parent_id)
        )
    ).all()

    lec_map = {kid: cnt for kid, cnt in lec_stats}
    tpl_map = {kid: cnt for kid, cnt in tpl_stats}
    child_map = {pid: cnt for pid, cnt in child_stats}

    out = []
    for kp in rows:
        data = KnowledgePointRead.model_validate(kp).model_dump()
        data["lecture_count"] = lec_map.get(kp.id, 0)
        data["template_count"] = tpl_map.get(kp.id, 0)
        data["children_count"] = child_map.get(kp.id, 0)
        out.append(KnowledgePointRead(**data))
    return out


@router.get("/", response_model=list[KnowledgePointRead])
async def list_knowledge_points(
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgePointRead]:
    stmt = select(KnowledgePoint).order_by(KnowledgePoint.order.asc(), KnowledgePoint.name.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return await _enrich_kp_rows(db, rows)


@router.get("/{kp_id}", response_model=KnowledgePointRead)
async def get_knowledge_point(
    kp_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> KnowledgePointRead:
    kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        raise HTTPException(status_code=404, detail="knowledge point not found")
    enriched = await _enrich_kp_rows(db, [kp])
    return enriched[0]


@router.get("/{kp_id}/lectures", response_model=list[LectureRead])
async def get_lectures(
    kp_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[LectureRead]:
    stmt = select(Lecture).where(Lecture.knowledge_id == kp_id).order_by(Lecture.level.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [LectureRead.model_validate(lecture) for lecture in rows]


@router.get("/{kp_id}/templates", response_model=list[CodeTemplateRead])
async def get_templates(
    kp_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[CodeTemplateRead]:
    """列出某知识点的代码模板（详情页展示用）。"""
    stmt = select(CodeTemplate).where(CodeTemplate.knowledge_id == kp_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [CodeTemplateRead.model_validate(t) for t in rows]


@router.get("/{kp_id}/prerequisites", response_model=list[KnowledgePointRead])
async def get_prerequisites(
    kp_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgePointRead]:
    """列出某知识点的前置知识点（学习依赖关系，详情页展示用）。"""
    stmt = (
        select(KnowledgePoint)
        .join(KnowledgePrerequisite, KnowledgePrerequisite.prerequisite_id == KnowledgePoint.id)
        .where(KnowledgePrerequisite.knowledge_id == kp_id)
        .order_by(KnowledgePoint.name)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return await _enrich_kp_rows(db, list(rows))
