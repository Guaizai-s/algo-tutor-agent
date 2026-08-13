"""Safely merge the bundled knowledge snapshot into the current database.

The bundled dump is a historical full-database snapshot.  Importing it with
``psql ON_ERROR_STOP=0`` used to mix user data with content data, fail on
out-of-order foreign keys, and still mark the import as successful.  This
module deliberately extracts only the four knowledge-content tables, loads
them into unconstrained temporary staging tables, and merges them in one
transaction.

The import marker is tied to the snapshot SHA-256, so replacing the snapshot
automatically triggers a new idempotent merge.  No users, submissions,
learning paths, progress, or Alembic state are read from the snapshot.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import text

from app.core.database import async_session_maker

SEED_FILE = Path(os.environ.get("SEED_FILE", "/app/seed_data.sql.gz"))
SEED_MARKER = "knowledge_snapshot_v2"

CONTENT_TABLES = (
    "knowledge_points",
    "lectures",
    "code_templates",
    "knowledge_prerequisites",
)


def seed_sha256(path: Path = SEED_FILE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_content_inserts(path: Path = SEED_FILE) -> Iterator[tuple[str, str]]:
    """Yield complete INSERT statements for allow-listed content tables.

    Statements contain lecture/template bodies with arbitrary newlines and
    semicolons, so completion is detected with SQL single-quote awareness
    rather than line endings alone.
    """

    prefix = "INSERT INTO public."
    with gzip.open(path, "rt", encoding="utf-8") as source:
        table: str | None = None
        parts: list[str] = []
        in_quote = False

        for line in source:
            if table is None:
                if not line.startswith(prefix):
                    continue
                candidate = line[len(prefix) :].split(" ", 1)[0]
                if candidate not in CONTENT_TABLES:
                    continue
                table = candidate
                parts = []
                in_quote = False

            parts.append(line)
            index = 0
            while index < len(line):
                char = line[index]
                if char == "'":
                    if in_quote and index + 1 < len(line) and line[index + 1] == "'":
                        index += 2
                        continue
                    in_quote = not in_quote
                elif char == ";" and not in_quote:
                    statement = "".join(parts)
                    yield table, statement
                    table = None
                    parts = []
                    break
                index += 1

        if table is not None:
            raise ValueError(f"unterminated INSERT statement for {table}")


def snapshot_counts(path: Path = SEED_FILE) -> dict[str, int]:
    counts = {table: 0 for table in CONTENT_TABLES}
    for table, _statement in _iter_content_inserts(path):
        counts[table] += 1
    return counts


def _staging_sql() -> str:
    return """
CREATE TEMP TABLE seed_knowledge_points (
    id uuid, name text, slug text, description text, difficulty knowledge_difficulty,
    parent_id uuid, sort_order integer, created_at timestamptz, updated_at timestamptz,
    cf_tag text, cf_problem_count integer
) ON COMMIT DROP;
CREATE TEMP TABLE seed_lectures (
    id uuid, knowledge_id uuid, level lecture_level, title text, content text,
    created_at timestamptz, updated_at timestamptz, source lecture_source,
    source_lecture_id uuid, rewrite_version integer, generation_prompt_hash text
) ON COMMIT DROP;
CREATE TEMP TABLE seed_code_templates (
    id uuid, knowledge_id uuid, language text, template_code text, explanation text,
    created_at timestamptz, updated_at timestamptz
) ON COMMIT DROP;
CREATE TEMP TABLE seed_knowledge_prerequisites (
    id uuid, knowledge_id uuid, prerequisite_id uuid
) ON COMMIT DROP;
"""


def _merge_sql(counts: dict[str, int], snapshot_hash: str) -> str:
    expected_checks = "\n".join(
        f"IF (SELECT count(*) FROM seed_{table}) <> {counts[table]} THEN "
        f"RAISE EXCEPTION 'staging count mismatch for {table}'; END IF;"
        for table in CONTENT_TABLES
    )
    stats_json = json.dumps(counts, sort_keys=True)
    return f"""
DO $seed_validate$
BEGIN
    {expected_checks}
    IF EXISTS (
        SELECT 1 FROM seed_knowledge_points child
        LEFT JOIN seed_knowledge_points parent ON parent.id = child.parent_id
        LEFT JOIN knowledge_points current_parent ON current_parent.id = child.parent_id
        WHERE child.parent_id IS NOT NULL AND parent.id IS NULL AND current_parent.id IS NULL
    ) THEN
        RAISE EXCEPTION 'knowledge snapshot contains an orphan parent_id';
    END IF;
END
$seed_validate$;

INSERT INTO knowledge_points (
    id, name, slug, description, difficulty, parent_id, "order", created_at,
    updated_at, cf_tag, cf_problem_count
)
SELECT id, name, slug, description, difficulty, NULL, sort_order, created_at,
       updated_at, cf_tag, cf_problem_count
FROM seed_knowledge_points
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    description = EXCLUDED.description,
    difficulty = EXCLUDED.difficulty,
    "order" = EXCLUDED."order",
    updated_at = EXCLUDED.updated_at,
    cf_tag = EXCLUDED.cf_tag,
    cf_problem_count = EXCLUDED.cf_problem_count;

-- Parent rows can appear after children in pg_dump's INSERT stream.  The
-- staging table is unconstrained, so insert/update every node first and then
-- restore the self reference once all IDs exist.
UPDATE knowledge_points target
SET parent_id = source.parent_id
FROM seed_knowledge_points source
WHERE target.id = source.id
  AND target.parent_id IS DISTINCT FROM source.parent_id;

INSERT INTO lectures (
    id, knowledge_id, level, title, content, created_at, updated_at, source,
    source_lecture_id, rewrite_version, generation_prompt_hash
)
SELECT id, knowledge_id, level, title, content, created_at, updated_at, source,
       NULL, rewrite_version, generation_prompt_hash
FROM seed_lectures
ON CONFLICT (id) DO UPDATE SET
    knowledge_id = EXCLUDED.knowledge_id,
    level = EXCLUDED.level,
    title = EXCLUDED.title,
    content = EXCLUDED.content,
    updated_at = EXCLUDED.updated_at,
    source = EXCLUDED.source,
    rewrite_version = EXCLUDED.rewrite_version,
    generation_prompt_hash = EXCLUDED.generation_prompt_hash;

UPDATE lectures target
SET source_lecture_id = source.source_lecture_id
FROM seed_lectures source
WHERE target.id = source.id
  AND target.source_lecture_id IS DISTINCT FROM source.source_lecture_id;

INSERT INTO code_templates (
    id, knowledge_id, language, template_code, explanation, created_at, updated_at
)
SELECT id, knowledge_id, language, template_code, explanation, created_at, updated_at
FROM seed_code_templates
ON CONFLICT (id) DO UPDATE SET
    knowledge_id = EXCLUDED.knowledge_id,
    language = EXCLUDED.language,
    template_code = EXCLUDED.template_code,
    explanation = EXCLUDED.explanation,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_prerequisites (id, knowledge_id, prerequisite_id)
SELECT id, knowledge_id, prerequisite_id
FROM seed_knowledge_prerequisites
ON CONFLICT (id) DO UPDATE SET
    knowledge_id = EXCLUDED.knowledge_id,
    prerequisite_id = EXCLUDED.prerequisite_id;

DO $seed_verify$
BEGIN
    IF (SELECT count(*) FROM seed_knowledge_points s JOIN knowledge_points t USING (id))
       <> {counts['knowledge_points']} THEN
        RAISE EXCEPTION 'knowledge point merge verification failed';
    END IF;
    IF (SELECT count(*) FROM seed_lectures s JOIN lectures t USING (id))
       <> {counts['lectures']} THEN
        RAISE EXCEPTION 'lecture merge verification failed';
    END IF;
    IF (SELECT count(*) FROM seed_code_templates s JOIN code_templates t USING (id))
       <> {counts['code_templates']} THEN
        RAISE EXCEPTION 'template merge verification failed';
    END IF;
    IF (SELECT count(*) FROM seed_knowledge_prerequisites s JOIN knowledge_prerequisites t USING (id))
       <> {counts['knowledge_prerequisites']} THEN
        RAISE EXCEPTION 'prerequisite merge verification failed';
    END IF;
END
$seed_verify$;

CREATE TABLE IF NOT EXISTS seed_meta (
    key text PRIMARY KEY,
    seed_sha256 text NOT NULL,
    stats jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    imported_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE seed_meta ADD COLUMN IF NOT EXISTS seed_sha256 text;
ALTER TABLE seed_meta ADD COLUMN IF NOT EXISTS stats jsonb NOT NULL DEFAULT '{{}}'::jsonb;
INSERT INTO seed_meta (key, seed_sha256, stats, imported_at)
VALUES ('{SEED_MARKER}', '{snapshot_hash}', '{stats_json}'::jsonb, now())
ON CONFLICT (key) DO UPDATE SET
    seed_sha256 = EXCLUDED.seed_sha256,
    stats = EXCLUDED.stats,
    imported_at = EXCLUDED.imported_at;
COMMIT;
"""


def build_import_sql(path: Path = SEED_FILE) -> tuple[str, dict[str, int], str]:
    snapshot_hash = seed_sha256(path)
    counts = {table: 0 for table in CONTENT_TABLES}
    statements: list[str] = ["BEGIN;\n", _staging_sql()]

    for table, statement in _iter_content_inserts(path):
        counts[table] += 1
        statements.append(statement.replace(f"public.{table}", f"seed_{table}", 1))

    missing = [table for table, count in counts.items() if count == 0]
    if missing:
        raise ValueError(f"knowledge snapshot is missing required tables: {', '.join(missing)}")

    statements.append(_merge_sql(counts, snapshot_hash))
    return "".join(statements), counts, snapshot_hash


def _postgres_environment() -> dict[str, str]:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://algo_tutor:algo_tutor_secret@postgres:5432/algo_tutor",
    )
    parsed = urlparse(url.replace("+asyncpg", ""))
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": parsed.hostname or "postgres",
            "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username or "algo_tutor"),
            "PGPASSWORD": unquote(parsed.password or ""),
            "PGDATABASE": parsed.path.lstrip("/") or "algo_tutor",
        }
    )
    return env


async def is_snapshot_imported(snapshot_hash: str) -> bool:
    async with async_session_maker() as db:
        try:
            has_hash_column = await db.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'seed_meta'
                          AND column_name = 'seed_sha256'
                    )
                    """
                )
            )
            if not has_hash_column.scalar():
                return False
            result = await db.execute(
                text("SELECT seed_sha256 = :hash FROM seed_meta WHERE key = :key"),
                {"key": SEED_MARKER, "hash": snapshot_hash},
            )
            return bool(result.scalar())
        except Exception:
            return False


def _run_psql_import(sql: str) -> tuple[int, str]:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sql", delete=False) as temp:
            temp.write(sql)
            temp_path = Path(temp.name)
        result = subprocess.run(
            ["psql", "--quiet", "--set", "ON_ERROR_STOP=1", "--file", str(temp_path)],
            capture_output=True,
            text=True,
            env=_postgres_environment(),
            timeout=180,
            check=False,
        )
        return result.returncode, result.stderr
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


async def import_seed_data() -> bool:
    if not SEED_FILE.exists():
        print(f"[seed] Seed file not found: {SEED_FILE}")
        return False

    snapshot_hash = await asyncio.to_thread(seed_sha256, SEED_FILE)
    if await is_snapshot_imported(snapshot_hash):
        print(f"[seed] Knowledge snapshot {snapshot_hash[:12]} already imported; skipping.")
        return True

    print(f"[seed] Preparing knowledge snapshot {snapshot_hash[:12]}...")
    try:
        sql, counts, _ = await asyncio.to_thread(build_import_sql, SEED_FILE)
        returncode, stderr = await asyncio.to_thread(_run_psql_import, sql)
        if returncode != 0:
            print(f"[seed] Import failed (psql exit {returncode}): {stderr[-1200:]}")
            return False
        print(f"[seed] Knowledge snapshot merged and verified: {counts}")
        return True
    except Exception as exc:
        print(f"[seed] Knowledge snapshot import failed: {exc}")
        return False


async def main() -> None:
    if not await import_seed_data():
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
