"""Deterministic demo-account reset for presentations and end-to-end checks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.discussion import Discussion, DiscussionComment
from app.models.knowledge import KnowledgePoint, Lecture
from app.models.learning import (
    CheckIn,
    DailyTask,
    DailyTaskItem,
    DailyTaskItemStatus,
    DailyTaskItemType,
    LearningPath,
    LearningPathItem,
    LearningProfile,
    PathItemKind,
    PathItemStatus,
    ReviewRecord,
    ReviewStage,
    UserKnowledgeState,
    UserLectureRead,
    UserProblemAC,
)
from app.models.notification import Notification, NotificationType
from app.models.problem import Problem, ProblemVariant
from app.models.user import TargetMedal, User, UserRole
from app.models.wrongbook import WrongBookEntry

DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEMO_EMAIL = "demo@algo-tutor.local"
DEMO_USERNAME = "演示学员"
DEMO_PASSWORD = "Demo123456!"


async def _delete_existing_demo_data(db: AsyncSession) -> None:
    demo_ids = list(
        (await db.execute(select(User.id).where(or_(User.email == DEMO_EMAIL, User.username == DEMO_USERNAME))))
        .scalars()
        .all()
    )
    if DEMO_USER_ID not in demo_ids:
        demo_ids.append(DEMO_USER_ID)

    # Legacy solution tables are not represented by ORM models.
    await db.execute(
        text("DELETE FROM solution_comments WHERE author_id = ANY(:ids)"),
        {"ids": demo_ids},
    )
    await db.execute(text("DELETE FROM solutions WHERE author_id = ANY(:ids)"), {"ids": demo_ids})
    await db.execute(delete(DiscussionComment).where(DiscussionComment.author_id.in_(demo_ids)))
    await db.execute(delete(Discussion).where(Discussion.author_id.in_(demo_ids)))
    await db.execute(delete(ProblemVariant).where(ProblemVariant.created_by.in_(demo_ids)))

    # Delete dependent learning data before submissions/users.
    for model in (
        WrongBookEntry,
        DailyTask,
        LearningPath,
        Notification,
        ReviewRecord,
        CheckIn,
        UserLectureRead,
        UserProblemAC,
        UserKnowledgeState,
        LearningProfile,
        RatingHistory,
        Submission,
        CodeforcesAccount,
    ):
        await db.execute(delete(model).where(model.user_id.in_(demo_ids)))
    await db.execute(delete(User).where(User.id.in_(demo_ids)))
    await db.flush()


async def reset_demo_account(db: AsyncSession) -> User:
    """Recreate one isolated account with a fixed, judge-friendly learning story."""
    await _delete_existing_demo_data(db)

    user = User(
        id=DEMO_USER_ID,
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        hashed_password=hash_password(DEMO_PASSWORD),
        role=UserRole.STUDENT,
        school="未来学习中心",
        cf_handle="demo_student",
        target_medal=TargetMedal.SILVER,
    )
    db.add(user)
    await db.flush()

    required_slugs = ["oi-binary-search", "oi-sliding-window", "oi-sorting"]
    knowledge_rows = (
        (await db.execute(select(KnowledgePoint).where(KnowledgePoint.slug.in_(required_slugs)))).scalars().all()
    )
    knowledge = {item.slug: item for item in knowledge_rows}
    missing = [slug for slug in required_slugs if slug not in knowledge]
    if missing:
        raise RuntimeError(f"演示知识点缺失：{', '.join(missing)}；请先运行 seed_db")

    binary = knowledge["oi-binary-search"]
    sliding = knowledge["oi-sliding-window"]
    sorting = knowledge["oi-sorting"]
    db.add(
        LearningProfile(
            user_id=user.id,
            target_rating_min=1200,
            target_rating_max=1600,
        )
    )
    db.add_all(
        [
            UserKnowledgeState(
                user_id=user.id,
                knowledge_id=binary.id,
                mastery=0.35,
                is_weak=True,
                consecutive_wa=2,
            ),
            UserKnowledgeState(
                user_id=user.id,
                knowledge_id=sliding.id,
                mastery=0.15,
                is_weak=True,
                consecutive_wa=3,
            ),
            UserKnowledgeState(
                user_id=user.id,
                knowledge_id=sorting.id,
                mastery=0.9,
                is_weak=False,
                consecutive_wa=0,
            ),
        ]
    )

    path = LearningPath(user_id=user.id, is_active=True)
    path.items = [
        LearningPathItem(
            knowledge_id=binary.id,
            position=1,
            kind=PathItemKind.REMEDIATION,
            status=PathItemStatus.ACTIVE,
        ),
        LearningPathItem(
            knowledge_id=sliding.id,
            position=2,
            kind=PathItemKind.NORMAL,
            status=PathItemStatus.PENDING,
        ),
        LearningPathItem(
            knowledge_id=sorting.id,
            position=3,
            kind=PathItemKind.NORMAL,
            status=PathItemStatus.DONE,
        ),
    ]
    db.add(path)

    binary_problem = (
        await db.execute(select(Problem).where(Problem.slug == "demo-binary-search"))
    ).scalar_one_or_none()
    sliding_problem = (
        await db.execute(select(Problem).where(Problem.slug == "demo-longest-substring"))
    ).scalar_one_or_none()
    sorting_problem = (
        await db.execute(select(Problem).where(Problem.slug == "demo-sort-numbers"))
    ).scalar_one_or_none()
    if binary_problem is None or sliding_problem is None or sorting_problem is None:
        raise RuntimeError("演示诊断题缺失；请先运行 python -m scripts.seed_demo")

    lecture = (
        await db.execute(
            select(Lecture).where(Lecture.knowledge_id == binary.id).order_by(Lecture.created_at.asc()).limit(1)
        )
    ).scalar_one_or_none()
    task = DailyTask(
        user_id=user.id,
        task_date=date.today(),
        knowledge_id=binary.id,
        is_remediation=True,
        missing_slots="",
    )
    position = 1
    if lecture is not None:
        task.items.append(
            DailyTaskItem(
                item_type=DailyTaskItemType.LECTURE_CARD,
                position=position,
                lecture_id=lecture.id,
                status=DailyTaskItemStatus.PENDING,
            )
        )
        position += 1
    for item_type, problem in (
        (DailyTaskItemType.TEMPLATE_PROBLEM, binary_problem),
        (DailyTaskItemType.APPLICATION_PROBLEM, sliding_problem),
    ):
        task.items.append(
            DailyTaskItem(
                item_type=item_type,
                position=position,
                problem_id=problem.id,
                status=DailyTaskItemStatus.PENDING,
            )
        )
        position += 1
    db.add(task)

    # Seed one solved exercise and one realistic CF wrong-answer record.
    db.add(UserProblemAC(user_id=user.id, problem_id=sorting_problem.id))
    wrong_problem = (
        await db.execute(select(Problem).where(Problem.cf_contest_id == 4, Problem.cf_index == "A"))
    ).scalar_one_or_none() or binary_problem
    now = datetime.now(UTC)
    accepted = Submission(
        cf_submission_id=990000000,
        user_id=user.id,
        problem_id=sorting_problem.id,
        contest_id=0,
        problem_index="DEMO",
        handle_snapshot="demo_student",
        verdict="OK",
        programming_language="GNU C++17",
        submitted_at=now - timedelta(days=1),
        time_consumed_ms=62,
        memory_consumed_bytes=1024,
        passed_test_count=5,
    )
    wrong = Submission(
        cf_submission_id=990000001,
        user_id=user.id,
        problem_id=wrong_problem.id,
        contest_id=wrong_problem.cf_contest_id or 4,
        problem_index=wrong_problem.cf_index or "A",
        handle_snapshot="demo_student",
        verdict="WRONG_ANSWER",
        programming_language="GNU C++17",
        submitted_at=now - timedelta(hours=2),
        time_consumed_ms=31,
        memory_consumed_bytes=0,
        passed_test_count=1,
    )
    db.add_all([accepted, wrong])
    await db.flush()
    db.add(
        WrongBookEntry(
            user_id=user.id,
            submission_id=wrong.id,
            problem_id=wrong.problem_id,
            verdict=wrong.verdict,
            retry_count=0,
            resolved=False,
        )
    )
    db.add(
        ReviewRecord(
            user_id=user.id,
            knowledge_id=sorting.id,
            stage=ReviewStage.STAGE_1,
            last_reviewed_at=now - timedelta(days=2),
            next_review_at=now - timedelta(minutes=10),
            review_count=1,
        )
    )
    db.add(CheckIn(user_id=user.id, check_date=date.today(), streak_days=3))
    db.add(
        RatingHistory(
            user_id=user.id,
            handle="demo_student",
            contest_id=990001,
            contest_name="演示周赛",
            rank=128,
            old_rating=1280,
            new_rating=1360,
            rated_at=now - timedelta(days=7),
        )
    )
    db.add(
        Notification(
            user_id=user.id,
            notification_type=NotificationType.REMEDIATION,
            title="二分查找专项补漏",
            body="根据最近练习表现，算法教练已安排知识讲解和两道递进练习。",
            related_knowledge_id=binary.id,
        )
    )
    await db.flush()
    return user
