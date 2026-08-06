"""用户 CF 历史或诊断题驱动的最小冷启动流程。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.codeforces import CodeforcesAccount, Submission
from app.models.learning import LearningPath, LearningProfile, UserKnowledgeState, UserProblemAC
from app.models.problem import (
    Problem,
    ProblemDifficulty,
    ProblemKnowledgePoint,
    ProblemSource,
    ProblemStatus,
)
from app.models.user import TargetMedal, User
from app.schemas.onboarding import ColdStartResponse, DiagnosticProblemRead, DiagnosticSubmitRequest
from app.services.codeforces.client import CodeforcesClient
from app.services.codeforces.sync import (
    sync_cf_tag_knowledge_mappings,
    sync_user_rating,
    sync_user_status,
)
from app.services.learning_path import generate_learning_path
from app.services.progress import recompute_mastery

CF_HISTORY_MIN_SUBMISSIONS = 20
DIAGNOSTIC_TOTAL = 15
DIAGNOSTIC_KNOWLEDGE_TARGET = 10
DIAGNOSTIC_QUOTAS = {
    ProblemDifficulty.EASY: 5,
    ProblemDifficulty.MEDIUM: 7,
    ProblemDifficulty.HARD: 3,
}


async def get_onboarding_status(db: AsyncSession, user: User) -> ColdStartResponse:
    account = await _get_account(db, user.id)
    submission_count = await _submission_count(db, user.id)
    path = await _get_active_path(db, user.id)
    if path is not None:
        return ColdStartResponse(
            completed=True,
            mode="cf_history" if submission_count >= CF_HISTORY_MIN_SUBMISSIONS else "diagnostic",
            cf_handle=account.handle if account else None,
            current_rating=account.current_rating if account else None,
            submission_count=submission_count,
            learning_path_id=path.id,
            message="冷启动已完成",
        )

    diagnostic = await select_diagnostic_problems(db)
    return ColdStartResponse(
        completed=False,
        mode="not_started",
        cf_handle=account.handle if account else None,
        current_rating=account.current_rating if account else None,
        submission_count=submission_count,
        diagnostic_problems=diagnostic,
        **_diagnostic_summary(diagnostic),
        message="可使用 CF 历史或诊断题完成冷启动",
    )


async def start_cold_start(
    db: AsyncSession,
    user: User,
    client: CodeforcesClient,
) -> ColdStartResponse:
    account = await _get_account(db, user.id)
    sync_error: str | None = None
    # CF 题库是全局内容源，即使当前用户未绑定 CF，也要把已同步题目的
    # cf_tags 映射到知识点，供诊断后的每日任务推荐使用。
    mapped = await sync_cf_tag_knowledge_mappings(db)

    if account is not None:
        status_result = await sync_user_status(db, account, client)
        rating_result = await sync_user_rating(db, account, client)
        errors = [str(result["error"]) for result in (status_result, rating_result) if result.get("error")]
        sync_error = "; ".join(errors) or None

    await _ensure_learning_profile(db, user, account.current_rating if account else None)
    submission_count = await _submission_count(db, user.id)

    if account is not None and submission_count >= CF_HISTORY_MIN_SUBMISSIONS and sync_error is None:
        mastery = await recompute_mastery(db, user.id)
        path = await generate_learning_path(db, user.id, preview_count=8)
        return ColdStartResponse(
            completed=True,
            mode="cf_history",
            cf_handle=account.handle,
            current_rating=account.current_rating,
            submission_count=submission_count,
            mapped_knowledge_points=mastery.updated,
            learning_path_id=path.id,
            message="已根据 Codeforces 历史生成初始掌握度和学习路径",
        )

    diagnostic = await select_diagnostic_problems(db)
    return ColdStartResponse(
        completed=False,
        mode="diagnostic_required",
        cf_handle=account.handle if account else None,
        current_rating=account.current_rating if account else None,
        submission_count=submission_count,
        mapped_knowledge_points=mapped,
        diagnostic_problems=diagnostic,
        **_diagnostic_summary(diagnostic),
        message="CF 提交不足 20 条，请完成诊断题" if account else "请完成诊断题以生成初始学习路径",
        sync_error=sync_error,
    )


async def submit_diagnostic(
    db: AsyncSession,
    user: User,
    payload: DiagnosticSubmitRequest,
) -> ColdStartResponse:
    allowed = {problem.id for problem in await select_diagnostic_problems(db)}
    submitted_ids = {item.problem_id for item in payload.results}
    if len(submitted_ids) != len(payload.results):
        raise ValueError("诊断结果包含重复题目")
    if not submitted_ids.issubset(allowed):
        raise ValueError("诊断结果包含不在当前题单中的题目")

    incorrect_knowledge_ids: set[UUID] = set()
    for item in payload.results:
        knowledge_ids = set(
            (
                await db.execute(
                    select(ProblemKnowledgePoint.knowledge_id).where(
                        ProblemKnowledgePoint.problem_id == item.problem_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if item.correct:
            await db.execute(
                pg_insert(UserProblemAC)
                .values(user_id=user.id, problem_id=item.problem_id)
                .on_conflict_do_nothing(constraint="uq_user_problem")
            )
        else:
            incorrect_knowledge_ids.update(knowledge_ids)

    mastery = await recompute_mastery(db, user.id)
    for knowledge_id in incorrect_knowledge_ids:
        state = (
            await db.execute(
                select(UserKnowledgeState).where(
                    UserKnowledgeState.user_id == user.id,
                    UserKnowledgeState.knowledge_id == knowledge_id,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            db.add(
                UserKnowledgeState(
                    user_id=user.id,
                    knowledge_id=knowledge_id,
                    mastery=0.0,
                    is_weak=True,
                    consecutive_wa=1,
                )
            )
        else:
            state.is_weak = True
            state.consecutive_wa = max(state.consecutive_wa, 1)

    account = await _get_account(db, user.id)
    await _ensure_learning_profile(db, user, account.current_rating if account else None)
    await db.flush()
    path = await generate_learning_path(db, user.id, preview_count=8)
    return ColdStartResponse(
        completed=True,
        mode="diagnostic",
        cf_handle=account.handle if account else None,
        current_rating=account.current_rating if account else None,
        submission_count=await _submission_count(db, user.id),
        mapped_knowledge_points=mastery.updated + len(incorrect_knowledge_ids),
        learning_path_id=path.id,
        message="诊断完成，已生成初始掌握度和学习路径",
    )


async def select_diagnostic_problems(db: AsyncSession) -> list[DiagnosticProblemRead]:
    """选取 5 易 + 7 中 + 3 难，并优先覆盖至少 10 个知识点。

    当内容库客观不足时返回可用子集，并通过 ``diagnostic_ready`` 暴露降级状态；
    选择过程完全确定，避免同一用户刷新后题单漂移。
    """
    candidates = list(
        (
            await db.execute(
                select(Problem)
                .where(
                    Problem.source == ProblemSource.PLATFORM,
                    Problem.status == ProblemStatus.PUBLISHED,
                )
                .options(selectinload(Problem.knowledge_points))
                .order_by(Problem.submit_count.desc(), Problem.created_at.asc(), Problem.slug.asc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    selected = _select_diagnostic_candidates(candidates)

    result: list[DiagnosticProblemRead] = []
    for problem in selected:
        knowledge_ids = [knowledge.id for knowledge in problem.knowledge_points]
        result.append(
            DiagnosticProblemRead(
                id=problem.id,
                title=problem.title,
                difficulty=problem.difficulty.value,
                cf_rating=problem.cf_rating,
                knowledge_point_ids=knowledge_ids,
            )
        )
    return result


def _select_diagnostic_candidates(candidates: list[Problem]) -> list[Problem]:
    """在难度配额内贪心最大化知识点覆盖，然后稳定补齐各配额。"""
    difficulty_order = {difficulty: index for index, difficulty in enumerate(DIAGNOSTIC_QUOTAS)}
    remaining = dict(DIAGNOSTIC_QUOTAS)
    selected: list[Problem] = []
    selected_ids: set[UUID] = set()
    covered: set[UUID] = set()

    def knowledge_ids(problem: Problem) -> set[UUID]:
        return {knowledge.id for knowledge in problem.knowledge_points}

    # 第一阶段：每次选择能带来最多新知识点的题，并严格占用对应难度配额。
    while len(covered) < DIAGNOSTIC_KNOWLEDGE_TARGET:
        eligible = [
            problem
            for problem in candidates
            if problem.id not in selected_ids and remaining.get(problem.difficulty, 0) > 0
        ]
        if not eligible:
            break
        eligible.sort(
            key=lambda problem: (
                -len(knowledge_ids(problem) - covered),
                difficulty_order.get(problem.difficulty, len(difficulty_order)),
                -problem.submit_count,
                problem.slug,
            )
        )
        chosen = eligible[0]
        new_knowledge = knowledge_ids(chosen) - covered
        if not new_knowledge:
            break
        selected.append(chosen)
        selected_ids.add(chosen.id)
        covered.update(new_knowledge)
        remaining[chosen.difficulty] -= 1

    # 第二阶段：按 5/7/3 配额稳定补齐。
    for difficulty in DIAGNOSTIC_QUOTAS:
        for problem in candidates:
            if remaining[difficulty] <= 0:
                break
            if problem.id in selected_ids or problem.difficulty != difficulty:
                continue
            selected.append(problem)
            selected_ids.add(problem.id)
            remaining[difficulty] -= 1

    # 某个难度内容不足时，用其他难度补齐总数，但仍保持确定性。
    for problem in candidates:
        if len(selected) >= DIAGNOSTIC_TOTAL:
            break
        if problem.id not in selected_ids:
            selected.append(problem)
            selected_ids.add(problem.id)

    selected.sort(
        key=lambda problem: (
            difficulty_order.get(problem.difficulty, len(difficulty_order)),
            -problem.submit_count,
            problem.slug,
        )
    )
    return selected[:DIAGNOSTIC_TOTAL]


def _diagnostic_summary(problems: list[DiagnosticProblemRead]) -> dict[str, int | bool]:
    knowledge_ids = {
        knowledge_id for problem in problems for knowledge_id in problem.knowledge_point_ids
    }
    problem_count = len(problems)
    knowledge_count = len(knowledge_ids)
    return {
        "diagnostic_problem_count": problem_count,
        "diagnostic_knowledge_count": knowledge_count,
        "diagnostic_ready": (
            problem_count == DIAGNOSTIC_TOTAL
            and knowledge_count >= DIAGNOSTIC_KNOWLEDGE_TARGET
        ),
    }


async def _ensure_learning_profile(db: AsyncSession, user: User, rating: int | None) -> LearningProfile:
    if rating is not None:
        if rating < 1200:
            target_min, target_max = 800, 1200
        elif rating < 1600:
            target_min, target_max = 1200, 1600
        elif rating < 2000:
            target_min, target_max = 1600, 2000
        else:
            target_min, target_max = 2000, 2400
    else:
        ranges = {
            TargetMedal.BRONZE: (800, 1200),
            TargetMedal.SILVER: (1200, 1600),
            TargetMedal.GOLD: (1600, 2000),
        }
        target_min, target_max = ranges.get(user.target_medal, (1200, 1600))

    profile = (
        await db.execute(select(LearningProfile).where(LearningProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        profile = LearningProfile(
            user_id=user.id,
            target_rating_min=target_min,
            target_rating_max=target_max,
        )
        db.add(profile)
    else:
        profile.target_rating_min = target_min
        profile.target_rating_max = target_max
    await db.flush()
    return profile


async def _get_account(db: AsyncSession, user_id: UUID) -> CodeforcesAccount | None:
    return (
        await db.execute(select(CodeforcesAccount).where(CodeforcesAccount.user_id == user_id))
    ).scalar_one_or_none()


async def _submission_count(db: AsyncSession, user_id: UUID) -> int:
    return (
        await db.execute(select(func.count(Submission.id)).where(Submission.user_id == user_id))
    ).scalar_one()


async def _get_active_path(db: AsyncSession, user_id: UUID) -> LearningPath | None:
    return (
        await db.execute(
            select(LearningPath).where(LearningPath.user_id == user_id, LearningPath.is_active.is_(True))
        )
    ).scalar_one_or_none()
