"""批量 AI 改写讲义脚本（Phase 1）。

将 OI-Wiki + 左程云原始讲义用 OpenAI 改写为统一风格的独家讲义。

运行方式：
    docker compose exec backend python -m scripts.rewrite_lectures
    docker compose exec backend python -m scripts.rewrite_lectures --kp-id <uuid>
    docker compose exec backend python -m scripts.rewrite_lectures --dry-run
    docker compose exec backend python -m scripts.rewrite_lectures --force
    docker compose exec backend python -m scripts.rewrite_lectures --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, Lecture, LectureSource
from app.services.lecture_generator import batch_rewrite_all


async def dry_run() -> None:
    """预览哪些知识点需要改写。"""
    async with async_session_maker() as db:
        # 有原始讲义的知识点
        kps_with_sources = (
            await db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.slug)
                .distinct()
                .join(Lecture, Lecture.knowledge_id == KnowledgePoint.id)
                .where(Lecture.source.in_([LectureSource.OI_WIKI, LectureSource.ZUO_LECTURE]))
            )
        ).all()

        rewritten_kp_ids = set(
            (await db.execute(select(Lecture.knowledge_id).where(Lecture.source == LectureSource.AI_REWRITTEN)))
            .scalars()
            .all()
        )

        pending = [kp for kp in kps_with_sources if kp[0] not in rewritten_kp_ids]
        done = [kp for kp in kps_with_sources if kp[0] in rewritten_kp_ids]

        print(f"知识点总数（有原始讲义）: {len(kps_with_sources)}")
        print(f"  已改写: {len(done)}")
        print(f"  待改写: {len(pending)}")
        print()
        if pending:
            print("待改写知识点（前 20 个）:")
            for kp_id, name, slug in pending[:20]:
                print(f"  {name} ({slug})")
            if len(pending) > 20:
                print(f"  ... 还有 {len(pending) - 20} 个")
        print()
        if done:
            print("已改写知识点（前 5 个）:")
            for kp_id, name, slug in done[:5]:
                print(f"  {name} ({slug})")


async def main() -> None:
    parser = argparse.ArgumentParser(description="批量 AI 改写讲义")
    parser.add_argument("--kp-id", type=str, default=None, help="只改写指定知识点")
    parser.add_argument("--dry-run", action="store_true", help="预览不改写")
    parser.add_argument("--force", action="store_true", help="强制覆盖已有改写")
    parser.add_argument("--limit", type=int, default=None, help="限制改写数量")
    args = parser.parse_args()

    if args.dry_run:
        await dry_run()
        return

    async with async_session_maker() as db:
        kp_ids = [UUID(args.kp_id)] if args.kp_id else None
        print("开始批量改写讲义...")
        print(f"  force: {args.force}")
        print(f"  limit: {args.limit or '全部'}")
        print()

        count = await batch_rewrite_all(db, kp_ids=kp_ids, force=args.force)
        print(f"\n完成！共改写 {count} 个知识点。")


if __name__ == "__main__":
    asyncio.run(main())
