"""提交记录查询 router (Role A, 只读查询)。

API:
- GET /submissions          提交记录列表（分页，筛选 problem_id/verdict）
- GET /submissions/{id}     提交详情

数据来源：Submission 模型（Role B 领地），只读不写。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.codeforces import Submission
from app.models.problem import Problem
from app.schemas.submission import (
    SubmissionDetailResponse,
    SubmissionListResponse,
    SubmissionRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("", response_model=SubmissionListResponse)
async def api_list_submissions(
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    problem_id: UUID | None = Query(None),
    verdict: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> SubmissionListResponse:
    filters = [Submission.user_id == user_id]
    if problem_id:
        filters.append(Submission.problem_id == problem_id)
    if verdict:
        filters.append(Submission.verdict == verdict)

    count_stmt = select(func.count(Submission.id)).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Submission)
        .where(*filters)
        .order_by(Submission.submitted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # 批量加载题目标题
    problem_ids = [sub.problem_id for sub in rows if sub.problem_id]
    title_map: dict[UUID, str] = {}
    if problem_ids:
        p_rows = (await db.execute(select(Problem.id, Problem.title).where(Problem.id.in_(problem_ids)))).all()
        title_map = {p.id: p.title for p in p_rows}

    items = [
        SubmissionRead(
            id=sub.id,
            cf_submission_id=sub.cf_submission_id,
            user_id=sub.user_id,
            problem_id=sub.problem_id,
            problem_title=title_map.get(sub.problem_id) if sub.problem_id else None,
            contest_id=sub.contest_id,
            problem_index=sub.problem_index,
            verdict=sub.verdict,
            programming_language=sub.programming_language,
            submitted_at=sub.submitted_at,
            time_consumed_ms=sub.time_consumed_ms,
            memory_consumed_bytes=sub.memory_consumed_bytes,
            passed_test_count=sub.passed_test_count,
        )
        for sub in rows
    ]

    return SubmissionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{submission_id}", response_model=SubmissionDetailResponse)
async def api_get_submission(
    submission_id: UUID,
    user_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> SubmissionDetailResponse:
    sub = (
        await db.execute(select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    problem_title = None
    problem_description = None
    problem_difficulty = None
    problem_cf_rating = None

    if sub.problem_id:
        problem = (await db.execute(select(Problem).where(Problem.id == sub.problem_id))).scalar_one_or_none()
        if problem:
            problem_title = problem.title
            problem_description = problem.description
            problem_difficulty = problem.difficulty.value
            problem_cf_rating = problem.cf_rating

    return SubmissionDetailResponse(
        id=sub.id,
        cf_submission_id=sub.cf_submission_id,
        user_id=sub.user_id,
        problem_id=sub.problem_id,
        problem_title=problem_title,
        contest_id=sub.contest_id,
        problem_index=sub.problem_index,
        verdict=sub.verdict,
        programming_language=sub.programming_language,
        submitted_at=sub.submitted_at,
        time_consumed_ms=sub.time_consumed_ms,
        memory_consumed_bytes=sub.memory_consumed_bytes,
        passed_test_count=sub.passed_test_count,
        problem_description=problem_description,
        problem_difficulty=problem_difficulty,
        problem_cf_rating=problem_cf_rating,
    )
