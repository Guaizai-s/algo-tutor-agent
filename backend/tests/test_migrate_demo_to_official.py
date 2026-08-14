import inspect

from sqlalchemy import CheckConstraint

from app.models.knowledge import KnowledgePrerequisite
from scripts.migrate_demo_to_official import (
    DEMO_TO_OFFICIAL_CF,
    MISSING_OFFICIAL_SPECS,
    PROBLEM_TO_OFFICIAL,
    migrate_demo_references,
)


def test_every_demo_node_has_an_official_destination() -> None:
    assert "demo-array-hash" in DEMO_TO_OFFICIAL_CF
    assert "demo-two-sum" in PROBLEM_TO_OFFICIAL


def test_historical_snapshot_gaps_are_self_contained() -> None:
    assert MISSING_OFFICIAL_SPECS.keys() == {
        "oi-binary-search",
        "oi-greedy",
        "oi-sorting",
        "oi-two-pointers",
    }


def test_reference_migration_covers_user_progress_tables() -> None:
    source = inspect.getsource(migrate_demo_references)
    for table in (
        "user_knowledge_states",
        "learning_path_items",
        "daily_tasks",
        "review_records",
        "user_lecture_reads",
        "problem_knowledge_points",
    ):
        assert table in source


def test_reference_migration_removes_edges_that_would_become_self_dependencies() -> None:
    source = inspect.getsource(migrate_demo_references)
    assert "DELETE FROM knowledge_prerequisites" in source
    assert "knowledge_id = :demo_id AND prerequisite_id = :official_id" in source
    assert "knowledge_id = :official_id AND prerequisite_id = :demo_id" in source


def test_prerequisite_model_declares_not_self_constraint() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in KnowledgePrerequisite.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints["ck_knowledge_prerequisites_not_self"] == "knowledge_id <> prerequisite_id"
