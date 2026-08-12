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
from app.core.deps import CurrentUserOptional
from app.models.knowledge import KnowledgePoint
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.schemas.problem import CodeExecutionRequest, CodeExecutionResponse, ProblemListResponse, ProblemRead
from app.services import judge as judge_service
from app.services.learning_path import record_attempt
from app.tools import code_execution

router = APIRouter(prefix="/problems", tags=["problems"])

# 一次判题最多执行的测试用例数（防止超大题集拖慢响应）
MAX_JUDGE_CASES = 12


def _normalize_exec_status(verdict: str) -> str:
    """把判题 verdict 映射为沙箱执行状态（保持前端既有 status 语义）。"""
    return {
        "AC": "success",
        "WA": "success",
        "TLE": "timeout",
        "RE": "runtime_error",
        "CE": "compile_error",
    }.get(verdict, "internal_error")


async def _judge_all_cases(
    p: Problem,
    req: CodeExecutionRequest,
    test_cases: list[dict],
    timeout_ms: int,
    memory_limit_mb: int,
) -> tuple[str, int, int, str, str]:
    """逐用例真实判题，返回 (verdict, passed, total, stdout, message)。

    任一用例失败即中断，返回对应 verdict（WA/TLE/RE/CE）。
    """
    passed = 0
    for tc in test_cases:
        result = await judge_service.judge(
            source_code=req.code,
            language=req.language,
            test_input=tc.get("input", ""),
            expected_output=tc.get("output", ""),
            timeout_ms=timeout_ms,
            memory_mb=memory_limit_mb,
        )
        if result.verdict == judge_service.Verdict.AC:
            passed += 1
            continue
        message = result.message or f"用例 {passed + 1}/{len(test_cases)} 未通过"
        return result.verdict.value, passed, len(test_cases), result.stdout, message
    return "AC", passed, len(test_cases), "", ""


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
    tag: str | None = Query(None, max_length=100),
    source: str | None = Query(None, max_length=50),
    sort: str | None = Query(None, pattern="^(newest|oldest|rating_asc|rating_desc|acceptance)$"),
    db: AsyncSession = Depends(get_db),
) -> ProblemListResponse:
    """题目列表：难度/关键词/标签/来源筛选 + 排序。

    tag 为 CF 风格标签（cf_tags JSONB 包含匹配），如 "dynamic programming"。
    """
    stmt = (
        select(Problem).where(Problem.status == ProblemStatus.PUBLISHED).options(selectinload(Problem.knowledge_points))
    )

    if difficulty:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Problem.title.ilike(like), Problem.description.ilike(like)))
    if tag:
        stmt = stmt.where(Problem.cf_tags.contains([tag]))
    if source:
        stmt = stmt.where(Problem.source == source)

    # Total count for pagination.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    order_by = {
        "newest": Problem.created_at.desc(),
        "oldest": Problem.created_at.asc(),
        "rating_asc": Problem.cf_rating.asc().nulls_last(),
        "rating_desc": Problem.cf_rating.desc().nulls_last(),
        "acceptance": (Problem.accepted_count / func.nullif(Problem.submit_count, 0)).desc().nulls_last(),
    }.get(sort, Problem.created_at.desc())

    offset = (page - 1) * page_size
    stmt = stmt.order_by(order_by).offset(offset).limit(page_size)
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
    tag: str | None = Query(None, max_length=100),
    sort: str | None = Query(None, pattern="^(newest|oldest|rating_asc|rating_desc|acceptance)$"),
    db: AsyncSession = Depends(get_db),
) -> ProblemListResponse:
    stmt = (
        select(Problem)
        .where(Problem.status == ProblemStatus.PUBLISHED)
        .join(Problem.knowledge_points)
        .where(KnowledgePoint.slug == slug)
        .options(selectinload(Problem.knowledge_points))
    )
    if tag:
        stmt = stmt.where(Problem.cf_tags.contains([tag]))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    order_by = {
        "newest": Problem.created_at.desc(),
        "oldest": Problem.created_at.asc(),
        "rating_asc": Problem.cf_rating.asc().nulls_last(),
        "rating_desc": Problem.cf_rating.desc().nulls_last(),
        "acceptance": (Problem.accepted_count / func.nullif(Problem.submit_count, 0)).desc().nulls_last(),
    }.get(sort, Problem.created_at.desc())

    offset = (page - 1) * page_size
    stmt = stmt.order_by(order_by).offset(offset).limit(page_size)
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
    user: CurrentUserOptional = None,
) -> CodeExecutionResponse:
    """在沙箱中直接运行代码，不让 LLM 参与执行关键路径。

    平台自建题（有 test_cases）：执行真实判题（全量用例），
    判定 AC/WA/TLE/RE/CE 并自动回传 record_attempt，打通
    「做题 → 掌握度/学习路径更新」数据闭环。
    Codeforces 外链题：没有同步题面和测试用例，使用空输入运行，
    并明确告知调用方该结果不代表 AC。
    """
    p = (
        await db.execute(
            select(Problem)
            .where(
                Problem.id == problem_id,
                Problem.status == ProblemStatus.PUBLISHED,
            )
            .options(selectinload(Problem.knowledge_points))
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="problem not found or not published")

    timeout_ms = max(100, min(p.time_limit_ms, settings.SANDBOX_MAX_TIMEOUT_MS))
    problem_memory_mb = math.ceil(p.memory_limit_kb / 1024)
    memory_limit_mb = max(16, min(problem_memory_mb, settings.SANDBOX_MAX_MEMORY_MB))

    test_cases = (getattr(p, "test_cases", None) or [])[:MAX_JUDGE_CASES]
    if test_cases:
        verdict, passed, total, stdout, fail_message = await _judge_all_cases(
            p, req, test_cases, timeout_ms, memory_limit_mb
        )
        # 判题统计（判题结论回写题目热度）
        p.submit_count += 1
        if verdict == "AC":
            p.accepted_count += 1
        # 结果回传：AC/WA/TLE/RE/CE 均记录，ERR（沙箱故障）不算作答
        knowledge_points = getattr(p, "knowledge_points", None) or []
        if user is not None and knowledge_points and verdict != "ERR":
            await record_attempt(db, user.id, knowledge_points[0].id, p.id, verdict)
        await db.commit()
        if verdict == "AC":
            message = f"全部 {total} 个测试用例通过，答案正确 (AC)"
        elif verdict == "ERR":
            message = f"判题服务暂时不可用，本次作答未记录：{fail_message} 请稍后重试。"
        else:
            message = f"答案错误 (verdict={verdict})：通过 {passed}/{total} 个用例。{fail_message}"
        # ERR（沙箱故障）对外归一化为 N/A，避免泄露内部错误码给前端
        resp_verdict = "N/A" if verdict == "ERR" else verdict
        return CodeExecutionResponse.model_validate(
            {
                "status": _normalize_exec_status(verdict),
                "stdout": stdout,
                "stderr": "",
                "exit_code": 0,
                "time_used_ms": 0,
                "truncated": False,
                "input_source": "sample",
                "message": message,
                "is_real_judge": True,
                "verdict": resp_verdict,
                "total_cases": total,
                "passed_cases": passed,
            }
        )

    # 无测试用例（CF 外链题）：仅运行样例/空输入，不判题、不回传
    input_source = "sample" if p.sample_input is not None else "empty"
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
            "is_real_judge": False,
            "verdict": "N/A",
            "total_cases": 0,
            "passed_cases": 0,
        }
    )
