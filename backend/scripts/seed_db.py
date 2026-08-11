"""种子数据自动导入脚本。

在 backend 容器启动时自动执行，检测 seed_data.sql.gz 是否存在且未导入，
若需要则自动导入。通过 seed_meta 表记录导入状态，确保只执行一次。
"""

import asyncio
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from app.core.database import async_session_maker

SEED_FILE = Path("/app/seed_data.sql.gz")
SEED_MARKER = "ai_rewritten_lectures_v1"


def _get_pg_url() -> str:
    """从 DATABASE_URL 环境变量构建 psql 连接字符串。"""
    url = os.environ.get("DATABASE_URL", "postgresql://algo_tutor:algo_tutor_secret@postgres:5432/algo_tutor")
    parsed = urlparse(url.replace("+asyncpg", ""))
    # URL-encode password for shell safety
    from urllib.parse import quote

    pw = quote(parsed.password or "", safe="")
    return f"postgresql://{parsed.username}:{pw}@{parsed.hostname}:{parsed.port or 5432}{parsed.path}"


async def is_seed_imported() -> bool:
    """检查种子数据是否已导入。"""
    async with async_session_maker() as db:
        try:
            result = await db.execute(
                text("SELECT EXISTS (SELECT 1 FROM seed_meta WHERE key = :key)"),
                {"key": SEED_MARKER},
            )
            return bool(result.scalar())
        except Exception:
            return False


async def ensure_seed_meta_table() -> None:
    """确保 seed_meta 表存在。"""
    async with async_session_maker() as db:
        try:
            await db.execute(
                text("""CREATE TABLE IF NOT EXISTS seed_meta (
                    key TEXT PRIMARY KEY,
                    imported_at TIMESTAMP DEFAULT NOW()
                )""")
            )
            await db.commit()
        except Exception:
            pass


async def mark_seed_imported() -> None:
    """记录种子数据已导入。"""
    async with async_session_maker() as db:
        await db.execute(
            text("INSERT INTO seed_meta (key) VALUES (:key) ON CONFLICT DO NOTHING"),
            {"key": SEED_MARKER},
        )
        await db.commit()


def _run_psql_import() -> tuple[int, str]:
    """通过 subprocess 调用 psql 导入种子数据。"""
    pg_url = _get_pg_url()
    cmd = f"zcat {SEED_FILE} | psql " f"{pg_url} " "--quiet -v ON_ERROR_STOP=0"
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=True,
        timeout=120,
    )
    return result.returncode, result.stderr


async def import_seed_data() -> bool:
    """导入种子数据文件。返回 True 表示成功。"""
    if not SEED_FILE.exists():
        print(f"[seed] Seed file not found: {SEED_FILE}")
        return False

    await ensure_seed_meta_table()

    if await is_seed_imported():
        print("[seed] Seed data already imported, skipping.")
        return True

    print(f"[seed] Importing seed data from {SEED_FILE}...")
    try:
        returncode, stderr = await asyncio.to_thread(_run_psql_import)

        if returncode != 0:
            print(f"[seed] psql exit {returncode}: {stderr[:300]}")
            return False

        # 忽略重复主键警告（正常现象）
        if stderr and "duplicate key" not in stderr and "already exists" not in stderr:
            print(f"[seed] psql stderr: {stderr[:200]}")

        await mark_seed_imported()
        print("[seed] Seed data imported successfully.")
        return True
    except Exception as e:
        print(f"[seed] Failed to import seed data: {e}")
        return False


async def main() -> None:
    success = await import_seed_data()
    if not success:
        print("[seed] Seed import skipped or failed, continuing startup...")


if __name__ == "__main__":
    asyncio.run(main())
