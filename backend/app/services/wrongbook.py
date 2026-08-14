"""错题本 service (Task 12)。

核心职责：
- 查询用户错题列表（基于 Submission 表的最终失败 verdict）
- 错题重试计数（使用 WrongBookEntry 独立模型，不跨区修改 Submission）
- 同类题推荐（基于知识点关联 + cf_rating 升序）

COMPAT: user_id 显式传入，等认证落地后改 token。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import Submission
from app.models.knowledge import KnowledgePoint
from app.models.problem import Problem, ProblemKnowledgePoint, ProblemStatus
from app.models.wrongbook import WrongBookEntry
from app.schemas.wrongbook import (
    RetryWrongBookResponse,
    WrongBookDetailResponse,
    WrongBookItem,
    WrongBookListParams,
    WrongBookListResponse,
    WrongBookRecommendation,
)
from app.services.codeforces.verdicts import WRONGBOOK_VERDICTS


async def list_wrongbook(db: AsyncSession, user_id: UUID, params: WrongBookListParams) -> WrongBookListResponse:
    """查询用户错题本列表。"""
    filters = [Submission.user_id == user_id, Submission.verdict.in_(WRONGBOOK_VERDICTS)]
    if params.knowledge_id:
        subq = select(ProblemKnowledgePoint.problem_id).where(ProblemKnowledgePoint.knowledge_id == params.knowledge_id)
        filters.append(Submission.problem_id.in_(subq))

    joined = Submission.__table__.outerjoin(
        WrongBookEntry.__table__,
        (WrongBookEntry.submission_id == Submission.id) & (WrongBookEntry.user_id == user_id),
    )
    if params.resolved is not None:
        resolved_value = func.coalesce(WrongBookEntry.resolved, False)
        filters.append(resolved_value.is_(params.resolved))

    count_stmt = select(func.count(Submission.id)).select_from(joined).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Submission, WrongBookEntry)
        .select_from(joined)
        .where(*filters)
        .order_by(Submission.submitted_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).all()

    items: list[WrongBookItem] = []
    for sub, wb in rows:
        item = await _build_wrongbook_item(db, sub, wb)
        items.append(item)

    return WrongBookListResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=max(1, (total + params.page_size - 1) // params.page_size),
    )


async def get_wrongbook_detail(db: AsyncSession, submission_id: UUID, user_id: UUID) -> WrongBookDetailResponse | None:
    """获取错题详情。"""
    sub = (
        await db.execute(select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None:
        return None

    wb = (
        await db.execute(select(WrongBookEntry).where(WrongBookEntry.submission_id == submission_id))
    ).scalar_one_or_none()

    item = await _build_wrongbook_item(db, sub, wb)

    detail = WrongBookDetailResponse(
        submission_id=sub.id,
        problem_id=sub.problem_id,
        problem_title=item.problem_title,
        cf_contest_id=sub.contest_id,
        cf_index=sub.problem_index,
        verdict=sub.verdict,
        knowledge_point_names=item.knowledge_point_names,
        retry_count=item.retry_count,
        resolved=item.resolved,
        submitted_at=sub.submitted_at,
        last_retry_at=item.last_retry_at,
        programming_language=sub.programming_language,
        time_consumed_ms=sub.time_consumed_ms,
        memory_consumed_bytes=sub.memory_consumed_bytes,
    )

    if sub.problem_id:
        problem = (await db.execute(select(Problem).where(Problem.id == sub.problem_id))).scalar_one_or_none()
        if problem:
            detail.problem_description = problem.description
            detail.problem_difficulty = problem.difficulty.value
            detail.problem_cf_rating = problem.cf_rating

    return detail


async def retry_wrongbook(db: AsyncSession, submission_id: UUID, user_id: UUID) -> RetryWrongBookResponse | None:
    """标记错题已重试。每次调用 retry_count + 1，重试 >= 3 次标记为已解决。"""
    sub = (
        await db.execute(select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None:
        return None

    # upsert WrongBookEntry
    wb = (
        await db.execute(select(WrongBookEntry).where(WrongBookEntry.submission_id == submission_id))
    ).scalar_one_or_none()

    if wb is None:
        wb = WrongBookEntry(
            user_id=user_id,
            submission_id=submission_id,
            problem_id=sub.problem_id,
            verdict=sub.verdict,
            retry_count=1,
            resolved=False,
            last_retry_at=datetime.now(UTC),
        )
        db.add(wb)
    else:
        wb.retry_count += 1
        wb.last_retry_at = datetime.now(UTC)
        if wb.retry_count >= 3:
            wb.resolved = True

    await db.flush()
    await db.refresh(wb)

    return RetryWrongBookResponse(
        submission_id=sub.id,
        retry_count=wb.retry_count,
        resolved=wb.resolved,
    )


async def get_recommendations(
    db: AsyncSession, submission_id: UUID, user_id: UUID, limit: int = 5
) -> list[WrongBookRecommendation]:
    """获取同类题推荐（基于知识点关联 + cf_rating 升序，排除已 AC 题目）。"""
    sub = (
        await db.execute(select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None or sub.problem_id is None:
        return []

    # 获取原题目的知识点
    kp_rows = (
        await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name)
            .join(ProblemKnowledgePoint, ProblemKnowledgePoint.knowledge_id == KnowledgePoint.id)
            .where(ProblemKnowledgePoint.problem_id == sub.problem_id)
        )
    ).all()
    if not kp_rows:
        return []

    kp_ids = [row.id for row in kp_rows]

    # 获取用户已 AC 的题目 ID
    from app.models.learning import UserProblemAC

    ac_ids = (
        (await db.execute(select(UserProblemAC.problem_id).where(UserProblemAC.user_id == user_id))).scalars().all()
    )

    # 查找同类知识点的已发布题目，排除已 AC 题目和原题，按 cf_rating 升序
    candidate_ids = (
        select(ProblemKnowledgePoint.problem_id).where(ProblemKnowledgePoint.knowledge_id.in_(kp_ids)).distinct()
    )
    stmt = (
        select(Problem)
        .where(
            Problem.id.in_(candidate_ids),
            Problem.status == ProblemStatus.PUBLISHED,
            Problem.id != sub.problem_id,
            ~Problem.id.in_(ac_ids) if ac_ids else True,
        )
        .order_by(Problem.cf_rating.asc().nulls_last(), Problem.submit_count.asc())
        .limit(limit)
    )
    problems = (await db.execute(stmt)).scalars().all()

    recommendations: list[WrongBookRecommendation] = []
    for p in problems:
        pkp_rows = (
            await db.execute(
                select(KnowledgePoint.name)
                .join(ProblemKnowledgePoint, ProblemKnowledgePoint.knowledge_id == KnowledgePoint.id)
                .where(ProblemKnowledgePoint.problem_id == p.id)
            )
        ).all()
        rec = WrongBookRecommendation(
            problem_id=p.id,
            title=p.title,
            difficulty=p.difficulty.value,
            cf_rating=p.cf_rating,
            knowledge_point_names=[row.name for row in pkp_rows],
            ac_count=p.accepted_count,
            submit_count=p.submit_count,
        )
        recommendations.append(rec)

    return recommendations


async def _build_wrongbook_item(db: AsyncSession, sub: Submission, wb: WrongBookEntry | None) -> WrongBookItem:
    """构建 WrongBookItem，填充知识点名称和题目标题。"""
    problem_title = None
    kp_names: list[str] = []

    if sub.problem_id:
        problem = (await db.execute(select(Problem).where(Problem.id == sub.problem_id))).scalar_one_or_none()
        if problem:
            problem_title = problem.title

        kp_rows = (
            await db.execute(
                select(KnowledgePoint.name)
                .join(ProblemKnowledgePoint, ProblemKnowledgePoint.knowledge_id == KnowledgePoint.id)
                .where(ProblemKnowledgePoint.problem_id == sub.problem_id)
            )
        ).all()
        kp_names = [row.name for row in kp_rows]

    return WrongBookItem(
        submission_id=sub.id,
        problem_id=sub.problem_id,
        problem_title=problem_title,
        cf_contest_id=sub.contest_id,
        cf_index=sub.problem_index,
        verdict=sub.verdict,
        knowledge_point_names=kp_names,
        retry_count=wb.retry_count if wb else 0,
        resolved=wb.resolved if wb else False,
        submitted_at=sub.submitted_at,
        last_retry_at=wb.last_retry_at if wb else None,
    )
