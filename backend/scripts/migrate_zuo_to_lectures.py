"""将左程云独立知识点迁移为对应 subtag/OI-wiki 知识点的讲义。

运行方式：
    docker compose exec backend python -m scripts.migrate_zuo_to_lectures --yes

策略：每个 zuo-* 知识点，将其讲义和模板代码迁移到最近的 subtag 节点（父节点），
然后删除 zuo-* 知识点。如果父节点也是 zuo-*，则递归向上查找。
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.core.database import async_session_maker
from app.models.knowledge import CodeTemplate, KnowledgePoint, Lecture


async def migrate(dry_run: bool = False) -> dict[str, int]:
    stats = {"migrated": 0, "lectures_moved": 0, "templates_moved": 0, "deleted": 0}

    async with async_session_maker() as session:
        # 获取所有 zuo-* 知识点
        result = await session.execute(
            select(KnowledgePoint).where(KnowledgePoint.slug.startswith("zuo-")).order_by(KnowledgePoint.slug)
        )
        zuo_kps = list(result.scalars().all())

        print(f"找到 {len(zuo_kps)} 个左程云知识点\n")

        for kp in zuo_kps:
            # 找到最近的 non-zuo 父节点
            target_id = kp.parent_id
            target = None
            while target_id:
                target = (
                    await session.execute(select(KnowledgePoint).where(KnowledgePoint.id == target_id))
                ).scalar_one_or_none()
                if target is None:
                    break
                if not target.slug.startswith("zuo-"):
                    break
                target_id = target.parent_id

            if target is None:
                print(f"  [skip] {kp.name} ({kp.slug}): 无有效父节点")
                continue

            # 查询该知识点的讲义和模板
            lectures = (await session.execute(select(Lecture).where(Lecture.knowledge_id == kp.id))).scalars().all()
            templates = (
                (await session.execute(select(CodeTemplate).where(CodeTemplate.knowledge_id == kp.id))).scalars().all()
            )

            print(
                f"  [migrate] {kp.name} ({kp.slug}) → {target.name} ({target.slug})  [{len(lectures)}讲, {len(templates)}模板]"
            )

            if dry_run:
                stats["migrated"] += 1
                stats["lectures_moved"] += len(lectures)
                stats["templates_moved"] += len(templates)
                continue

            # 移动讲义
            for lec in lectures:
                existing = (
                    await session.execute(
                        select(Lecture).where(
                            Lecture.knowledge_id == target.id,
                            Lecture.title == lec.title,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    lec.knowledge_id = target.id
                    stats["lectures_moved"] += 1
                else:
                    await session.delete(lec)
            await session.flush()

            # 移动模板代码
            for tpl in templates:
                tpl.knowledge_id = target.id
                stats["templates_moved"] += 1
            await session.flush()

            # 移动 problem_knowledge_points 关联
            await session.execute(
                text("UPDATE problem_knowledge_points SET knowledge_id = :target_id " "WHERE knowledge_id = :zuo_id"),
                {"target_id": target.id, "zuo_id": kp.id},
            )

            # 删除左程云知识点
            await session.delete(kp)
            stats["deleted"] += 1
            stats["migrated"] += 1

        await session.commit()

    return stats


async def main() -> None:
    auto_yes = "--yes" in sys.argv or "-y" in sys.argv
    dry_run_only = "--dry-run" in sys.argv

    if dry_run_only:
        print("=== Dry Run ===\n")
        stats = await migrate(dry_run=True)
        print(f"\n将迁移: {stats['migrated']}")
        print(f"将移动讲义: {stats['lectures_moved']}")
        print(f"将移动模板: {stats['templates_moved']}")
        return

    print("=== 迁移左程云知识点 → 对应 subtag ===\n")
    stats = await migrate(dry_run=True)
    print(f"\n将迁移 {stats['migrated']} 个知识点")
    print(f"将移动 {stats['lectures_moved']} 个讲义")
    print(f"将移动 {stats['templates_moved']} 个模板")

    if stats["migrated"] == 0:
        print("\n没有需要迁移的左程云知识点。")
        return

    if not auto_yes:
        print("\n使用 --yes 参数自动确认执行。")
        return

    print("\n执行迁移...")
    stats = await migrate(dry_run=False)
    print("\n迁移完成:")
    print(f"  已迁移: {stats['migrated']}")
    print(f"  已移动讲义: {stats['lectures_moved']}")
    print(f"  已移动模板: {stats['templates_moved']}")
    print(f"  已删除: {stats['deleted']}")


if __name__ == "__main__":
    asyncio.run(main())
