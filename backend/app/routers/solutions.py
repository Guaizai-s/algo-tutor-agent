"""题解广场 router (Task 15)。

API:
- GET    /solutions?problem_id=    列表（按题目筛选）
- GET    /solutions/{id}           详情
- POST   /solutions                发布题解
- PUT    /solutions/{id}           编辑
- DELETE /solutions/{id}           删除
- POST   /solutions/{id}/like      点赞
- POST   /solutions/{id}/comments      评论
- DELETE /solutions/{id}/comments/{cid}  删评论

COMPAT: author_id 显式从查询参数/请求体传入，等认证落地后改为 token 解析。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.problem import Problem, Solution, SolutionComment
from app.schemas.common import BaseSchema, PageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/solutions", tags=["solutions"])


# ── Schemas ──


class SolutionCreate(BaseSchema):
    problem_id: UUID
    title: str
    content: str
    language: str | None = None
    code: str | None = None


class SolutionUpdate(BaseSchema):
    title: str | None = None
    content: str | None = None
    language: str | None = None
    code: str | None = None


class SolutionRead(BaseSchema):
    id: UUID
    problem_id: UUID
    author_id: UUID
    title: str
    content: str
    language: str | None
    code: str | None
    is_featured: bool
    like_count: int
    created_at: str
    updated_at: str


class SolutionListResponse(PageResponse[SolutionRead]):
    pass


class SolutionCommentCreate(BaseSchema):
    content: str
    parent_id: UUID | None = None


class SolutionCommentRead(BaseSchema):
    id: UUID
    solution_id: UUID
    author_id: UUID
    content: str
    parent_id: UUID | None
    created_at: str
    updated_at: str
    replies: list[SolutionCommentRead] = []


class SolutionDetailResponse(SolutionRead):
    comments: list[SolutionCommentRead] = []


# ── Helpers ──


def _solution_to_read(s: Solution) -> SolutionRead:
    return SolutionRead(
        id=s.id,
        problem_id=s.problem_id,
        author_id=s.author_id,
        title=s.title,
        content=s.content,
        language=s.language,
        code=s.code,
        is_featured=s.is_featured,
        like_count=s.like_count,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


def _comment_to_tree(comments: list[SolutionComment]) -> list[SolutionCommentRead]:
    comment_map: dict[UUID, SolutionCommentRead] = {}
    roots: list[SolutionCommentRead] = []

    for c in comments:
        node = SolutionCommentRead(
            id=c.id,
            solution_id=c.solution_id,
            author_id=c.author_id,
            content=c.content,
            parent_id=c.parent_id,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
            replies=[],
        )
        comment_map[c.id] = node

    for c in comments:
        node = comment_map[c.id]
        if c.parent_id and c.parent_id in comment_map:
            comment_map[c.parent_id].replies.append(node)
        else:
            roots.append(node)

    return roots


# ── Routes ──


@router.get("", response_model=SolutionListResponse)
async def api_list_solutions(
    problem_id: UUID = Query(..., description="题目 ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> SolutionListResponse:
    # 验证题目存在
    p_exists = (await db.execute(select(Problem.id).where(Problem.id == problem_id))).scalar_one_or_none()
    if p_exists is None:
        raise HTTPException(status_code=404, detail="problem not found")

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

    return SolutionListResponse(
        items=[_solution_to_read(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{solution_id}", response_model=SolutionDetailResponse)
async def api_get_solution(
    solution_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SolutionDetailResponse:
    stmt = select(Solution).where(Solution.id == solution_id).options(selectinload(Solution.comments))
    solution = (await db.execute(stmt)).scalar_one_or_none()
    if solution is None:
        raise HTTPException(status_code=404, detail="solution not found")

    result = _solution_to_read(solution)
    return SolutionDetailResponse(
        **result.model_dump(),
        comments=_comment_to_tree(list(solution.comments)),
    )


@router.post("", response_model=SolutionRead, status_code=201)
async def api_create_solution(
    data: SolutionCreate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> SolutionRead:
    # 验证题目存在
    p_exists = (await db.execute(select(Problem.id).where(Problem.id == data.problem_id))).scalar_one_or_none()
    if p_exists is None:
        raise HTTPException(status_code=404, detail="problem not found")

    solution = Solution(
        problem_id=data.problem_id,
        author_id=author_id,
        title=data.title,
        content=data.content,
        language=data.language,
        code=data.code,
    )
    db.add(solution)
    await db.flush()
    await db.refresh(solution)
    return _solution_to_read(solution)


@router.put("/{solution_id}", response_model=SolutionRead)
async def api_update_solution(
    solution_id: UUID,
    data: SolutionUpdate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> SolutionRead:
    solution = (
        await db.execute(select(Solution).where(Solution.id == solution_id, Solution.author_id == author_id))
    ).scalar_one_or_none()
    if solution is None:
        raise HTTPException(status_code=404, detail="solution not found or not authorized")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(solution, key, value)
    await db.flush()
    await db.refresh(solution)
    return _solution_to_read(solution)


@router.delete("/{solution_id}", status_code=204, response_class=Response)
async def api_delete_solution(
    solution_id: UUID,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
):
    solution = (
        await db.execute(select(Solution).where(Solution.id == solution_id, Solution.author_id == author_id))
    ).scalar_one_or_none()
    if solution is None:
        raise HTTPException(status_code=404, detail="solution not found or not authorized")
    await db.delete(solution)
    await db.flush()


@router.post("/{solution_id}/like", response_model=SolutionRead)
async def api_like_solution(
    solution_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SolutionRead:
    solution = (await db.execute(select(Solution).where(Solution.id == solution_id))).scalar_one_or_none()
    if solution is None:
        raise HTTPException(status_code=404, detail="solution not found")
    solution.like_count += 1
    # spec: 点赞 >= 10 自动标记为精选题解
    if solution.like_count >= 10:
        solution.is_featured = True
    await db.flush()
    await db.refresh(solution)
    return _solution_to_read(solution)


@router.post("/{solution_id}/comments", response_model=SolutionCommentRead, status_code=201)
async def api_create_solution_comment(
    solution_id: UUID,
    data: SolutionCommentCreate,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
) -> SolutionCommentRead:
    # 验证题解存在
    exists = (await db.execute(select(Solution.id).where(Solution.id == solution_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="solution not found")

    # 验证 parent_id 存在且属于同一 solution
    if data.parent_id:
        parent = (
            await db.execute(
                select(SolutionComment).where(
                    SolutionComment.id == data.parent_id,
                    SolutionComment.solution_id == solution_id,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=404, detail="parent comment not found")

    comment = SolutionComment(
        solution_id=solution_id,
        author_id=author_id,
        content=data.content,
        parent_id=data.parent_id,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    return SolutionCommentRead(
        id=comment.id,
        solution_id=comment.solution_id,
        author_id=comment.author_id,
        content=comment.content,
        parent_id=comment.parent_id,
        created_at=comment.created_at.isoformat(),
        updated_at=comment.updated_at.isoformat(),
        replies=[],
    )


@router.delete("/{solution_id}/comments/{comment_id}", status_code=204, response_class=Response)
async def api_delete_solution_comment(
    solution_id: UUID,
    comment_id: UUID,
    author_id: UUID = Query(..., description="COMPAT: 认证落地后从 token 解析"),
    db: AsyncSession = Depends(get_db),
):
    comment = (
        await db.execute(
            select(SolutionComment).where(
                SolutionComment.id == comment_id,
                SolutionComment.solution_id == solution_id,
                SolutionComment.author_id == author_id,
            )
        )
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="comment not found or not authorized")
    await db.delete(comment)
    await db.flush()
