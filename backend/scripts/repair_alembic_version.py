"""Repair duplicate Alembic version rows left by the historical seed dump."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.database import async_session_maker


def _ancestor_revisions(script: ScriptDirectory, revision: str) -> set[str]:
    current = script.get_revision(revision)
    ancestors: set[str] = set()
    while current is not None:
        ancestors.add(current.revision)
        down = current.down_revision
        if down is None:
            break
        if not isinstance(down, str):
            raise RuntimeError("branched Alembic history requires manual repair")
        current = script.get_revision(down)
    return ancestors


def choose_canonical_revision(script: ScriptDirectory, revisions: set[str]) -> str:
    candidates = [revision for revision in revisions if revisions <= _ancestor_revisions(script, revision)]
    if len(candidates) != 1:
        raise RuntimeError(f"cannot safely choose one Alembic revision from {sorted(revisions)}")
    return candidates[0]


async def main() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    async with async_session_maker() as session:
        try:
            rows = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        except Exception:
            print("[alembic-repair] version table does not exist yet; skipping.")
            return

        revisions = set(rows)
        if len(revisions) <= 1:
            print("[alembic-repair] version table is already canonical.")
            return

        canonical = choose_canonical_revision(script, revisions)
        await session.execute(
            text("DELETE FROM alembic_version WHERE version_num <> :revision"), {"revision": canonical}
        )
        await session.commit()
        print(f"[alembic-repair] kept {canonical}; removed {len(revisions) - 1} ancestor row(s).")


if __name__ == "__main__":
    asyncio.run(main())
