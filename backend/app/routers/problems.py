"""Problems router.

Returns published problems. Never exposes test_cases in any response.
"""

from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.knowledge import KnowledgePoint
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.schemas.problem import CodeExecutionRequest, CodeExecutionResponse, ProblemListResponse, ProblemRead
from app.tools import code_execution

router = APIRouter(prefix="/problems", tags=["problems"])


def _to_read(p: Problem) -> ProblemRead:
    return ProblemRead.model_validate(
        {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "description": p.description,
            "difficulty": p.difficulty,
            "status": p.status,
            "time_limit_ms": p.time_limit_ms,
            "memory_limit_kb": p.memory_limit_kb,
            "sample_input": p.sample_input,
            "sample_output": p.sample_output,
            "hints": p.hints,
            "solution_template": p.solution_template,
            "knowledge_point_ids": [kp.id for kp in (p.knowledge_points or [])],
            "source": p.source,
            "external_url": p.external_url,
            "cf_tags": p.cf_tags,
            "submit_count": p.submit_count,
            "accepted_count": p.accepted_count,
            "cf_rating": p.cf_rating,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
    )


@router.get("/", response_model=ProblemListResponse)
async def list_problems(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    difficulty: ProblemDifficulty | None = None,
    search: str | None = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> ProblemListResponse:
    stmt = (
        select(Problem).where(Problem.status == ProblemStatus.PUBLISHED).options(selectinload(Problem.knowledge_points))
    )

    if difficulty:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Problem.title.ilike(like), Problem.description.ilike(like)))

    # Total count for pagination.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Problem.created_at.desc()).offset(offset).limit(page_size)
    problems = (await db.execute(stmt)).scalars().all()

    total_pages = (total + page_size - 1) // page_size if total else 0
    return ProblemListResponse(
        items=[_to_read(p) for p in problems],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# Static route declared BEFORE the dynamic /{problem_id} route so that
# /by-knowledge/{slug} is not swallowed by UUID parsing.
@router.get("/by-knowledge/{slug}", response_model=ProblemListResponse)
async def list_problems_by_knowledge(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ProblemListResponse:
    stmt = (
        select(Problem)
        .where(Problem.status == ProblemStatus.PUBLISHED)
        .join(Problem.knowledge_points)
        .where(KnowledgePoint.slug == slug)
        .options(selectinload(Problem.knowledge_points))
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Problem.created_at.desc()).offset(offset).limit(page_size)
    problems = (await db.execute(stmt)).scalars().all()

    total_pages = (total + page_size - 1) // page_size if total else 0
    return ProblemListResponse(
        items=[_to_read(p) for p in problems],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{problem_id}", response_model=ProblemRead)
async def get_problem(
    problem_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProblemRead:
    stmt = (
        select(Problem)
        .where(
            Problem.id == problem_id,
            Problem.status == ProblemStatus.PUBLISHED,
        )
        .options(selectinload(Problem.knowledge_points))
    )
    p = (await db.execute(stmt)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="problem not found or not published")
    return _to_read(p)


@router.post("/{problem_id}/execute", response_model=CodeExecutionResponse)
async def execute_problem_code(
    problem_id: UUID,
    req: CodeExecutionRequest,
    db: AsyncSession = Depends(get_db),
) -> CodeExecutionResponse:
    """在沙箱中直接运行代码，不让 LLM 参与执行关键路径。

    有样例输入时使用样例输入；Codeforces 外链题目前没有同步题面和样例，
    因此只能使用空输入运行，并明确告知调用方该结果不代表 AC。
    """
    p = (
        await db.execute(
            select(Problem).where(
                Problem.id == problem_id,
                Problem.status == ProblemStatus.PUBLISHED,
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="problem not found or not published")

    input_source = "sample" if p.sample_input is not None else "empty"
    timeout_ms = max(100, min(p.time_limit_ms, settings.SANDBOX_MAX_TIMEOUT_MS))
    problem_memory_mb = math.ceil(p.memory_limit_kb / 1024)
    memory_limit_mb = max(16, min(problem_memory_mb, settings.SANDBOX_MAX_MEMORY_MB))

    result = await code_execution.execute(
        {
            "language": req.language,
            "code": req.code,
            "stdin": p.sample_input or "",
            "timeout_ms": timeout_ms,
            "memory_limit_mb": memory_limit_mb,
        }
    )
    message = (
        "已使用题目样例输入运行；运行成功不等于通过全部测试。"
        if input_source == "sample"
        else "题目未提供样例输入，已使用空输入运行；此结果不代表通过题目。"
    )
    return CodeExecutionResponse.model_validate(
        {
            **result,
            "input_source": input_source,
            "message": message,
        }
    )


@router.get("/{problem_id}/solutions")
async def api_get_problem_solutions(
    problem_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取题目关联的题解列表（前端兼容路径，转发到 solutions 服务）。"""
    from app.models.problem import Solution
    from app.routers.solutions import _solution_to_read

    count_stmt = select(func.count(Solution.id)).where(Solution.problem_id == problem_id)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Solution)
        .where(Solution.problem_id == problem_id)
        .order_by(Solution.is_featured.desc(), Solution.like_count.desc(), Solution.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [_solution_to_read(r).model_dump() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }
