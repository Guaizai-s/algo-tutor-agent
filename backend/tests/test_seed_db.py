from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from scripts.seed_db import CONTENT_TABLES, _iter_content_inserts, build_import_sql


def _write_snapshot(path: Path, body: str) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as target:
        target.write(body)
    return path


def test_content_parser_handles_multiline_semicolons_and_filters_tables(tmp_path: Path) -> None:
    snapshot = _write_snapshot(
        tmp_path / "seed.sql.gz",
        """
INSERT INTO public.alembic_version VALUES ('old');
INSERT INTO public.users VALUES ('private-user');
INSERT INTO public.knowledge_points VALUES ('1', 'name', 'slug', NULL, 'easy', NULL, 0, now(), now(), NULL, 0);
INSERT INTO public.lectures VALUES ('2', '1', 'card', 'title', 'line one;\nline two with '');''', now(), now(), 'oi_wiki', NULL, 1, NULL);
INSERT INTO public.code_templates VALUES ('3', '1', 'cpp', 'int main() {\n  return 0;\n}', NULL, now(), now());
INSERT INTO public.knowledge_prerequisites VALUES ('4', '1', '1');
""",
    )

    rows = list(_iter_content_inserts(snapshot))
    assert [table for table, _ in rows] == list(CONTENT_TABLES)
    assert "line one;" in rows[1][1]
    assert all("alembic_version" not in statement for _, statement in rows)
    assert all("public.users" not in statement for _, statement in rows)


def test_build_import_sql_uses_staging_transaction_and_hash_marker(tmp_path: Path) -> None:
    snapshot = _write_snapshot(
        tmp_path / "seed.sql.gz",
        "\n".join(
            [
                "INSERT INTO public.knowledge_points VALUES ('1', 'n', 's', NULL, 'easy', NULL, 0, now(), now(), NULL, 0);",
                "INSERT INTO public.lectures VALUES ('2', '1', 'card', 't', 'c', now(), now(), 'oi_wiki', NULL, 1, NULL);",
                "INSERT INTO public.code_templates VALUES ('3', '1', 'cpp', 'c', NULL, now(), now());",
                "INSERT INTO public.knowledge_prerequisites VALUES ('4', '1', '1');",
            ]
        ),
    )

    sql, counts, digest = build_import_sql(snapshot)
    assert sql.startswith("BEGIN;")
    assert sql.rstrip().endswith("COMMIT;")
    assert "seed_knowledge_points" in sql
    assert "ON CONFLICT (id) DO UPDATE" in sql
    assert "knowledge_snapshot_v2" in sql
    assert digest in sql
    assert counts == {table: 1 for table in CONTENT_TABLES}
    assert "alembic_version" not in sql
    assert "public.users" not in sql


def test_build_import_sql_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    snapshot = _write_snapshot(
        tmp_path / "seed.sql.gz",
        "INSERT INTO public.knowledge_points VALUES ('1', 'n', 's', NULL, 'easy', NULL, 0, now(), now(), NULL, 0);",
    )
    with pytest.raises(ValueError, match="missing required tables"):
        build_import_sql(snapshot)
