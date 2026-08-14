"""Deterministic golden-demo data tests."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.codeforces import Submission
from app.models.knowledge import KnowledgePoint, Lecture, LectureLevel
from app.models.learning import LearningPath
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.models.user import User
from app.models.wrongbook import WrongBookEntry
from app.services.demo import DEMO_EMAIL, reset_demo_account


async def _seed_demo_dependencies(db_session) -> None:  # type: ignore[no-untyped-def]
    knowledge = {}
    for order, (slug, name) in enumerate(
        [
            ("oi-binary-search", "测试二分查找"),
            ("oi-sliding-window", "测试滑动窗口"),
            ("oi-sorting", "测试排序"),
        ]
    ):
        item = KnowledgePoint(slug=slug, name=name, order=order)
        db_session.add(item)
        knowledge[slug] = item
    await db_session.flush()
    db_session.add(
        Lecture(
            knowledge_id=knowledge["oi-binary-search"].id,
            level=LectureLevel.CARD,
            title="二分查找速览",
            content="维护单调搜索区间。",
        )
    )
    for slug, title, knowledge_slug in (
        ("demo-binary-search", "有序数组二分查找（验证题）", "oi-binary-search"),
        ("demo-longest-substring", "无重复字符的最长子串（验证题）", "oi-sliding-window"),
        ("demo-sort-numbers", "整数排序（诊断题）", "oi-sorting"),
    ):
        problem = Problem(
            slug=slug,
            title=title,
            description="演示题",
            difficulty=ProblemDifficulty.EASY,
            status=ProblemStatus.PUBLISHED,
            test_cases=[],
        )
        problem.knowledge_points.append(knowledge[knowledge_slug])
        db_session.add(problem)
    await db_session.flush()


async def test_reset_demo_account_is_idempotent(db_session):
    await _seed_demo_dependencies(db_session)

    first = await reset_demo_account(db_session)
    second = await reset_demo_account(db_session)

    assert first.id == second.id
    assert (await db_session.execute(select(func.count(User.id)).where(User.email == DEMO_EMAIL))).scalar_one() == 1
    assert (
        await db_session.execute(select(func.count(LearningPath.id)).where(LearningPath.user_id == second.id))
    ).scalar_one() == 1
    assert (
        await db_session.execute(select(func.count(Submission.id)).where(Submission.user_id == second.id))
    ).scalar_one() == 2
    assert (
        await db_session.execute(select(func.count(WrongBookEntry.id)).where(WrongBookEntry.user_id == second.id))
    ).scalar_one() == 1
