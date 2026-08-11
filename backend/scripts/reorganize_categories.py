"""整理知识点一级分类：新增「入门」分类并归位错位知识点。

问题背景：
  之前 seed/merge 把大量本不属于「基础」的知识点塞进了 cat-基础，
  包括 10 个搜索类、6 个竞赛类、1 个数学符号表、6 个入门级知识点。
  这导致 Progress 页面「基础」分组混入无关内容，KnowledgeTree 分类语义混乱。

迁移只改 parent_id，不影响题目关联 / 讲义 / 掌握度（均按 knowledge_id 关联）。
分类映射从 _classification_config.REALLOCATE_MAP 导入，与 enrichment/seeding 保持一致。

运行方式：
    docker compose exec backend python -m scripts.reorganize_categories

幂等：重复运行不会产生副作用，已归位的知识点保持不变。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, KnowledgePointDifficulty
from scripts._classification_config import REALLOCATE_MAP

# 新建的一级分类根节点配置：slug → (name, order, difficulty)
# 注：这些根节点如已由 seed_knowledge_graph 创建则只更新元数据
NEW_CATEGORY_ROOTS: dict[str, tuple[str, int, KnowledgePointDifficulty]] = {
    "cat-入门": ("入门分类", -1000, KnowledgePointDifficulty.EASY),
    "cat-搜索": ("搜索分类", 5000, KnowledgePointDifficulty.MEDIUM),
    "cat-竞赛": ("竞赛分类", 11000, KnowledgePointDifficulty.HARD),
}

# 已有的一级分类根节点 slug（用于数学符号表归位）
MATH_ROOT_SLUG = "cat-数学"


async def main() -> None:
    async with async_session_maker() as session:
        # 1) 创建新的一级分类根节点
        root_by_slug: dict[str, KnowledgePoint] = {}
        # 同时加载已有根节点（数学）
        all_root_slugs = set(NEW_CATEGORY_ROOTS.keys()) | {MATH_ROOT_SLUG}
        existing = (
            (await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug.in_(all_root_slugs))))
            .scalars()
            .all()
        )
        for kp in existing:
            root_by_slug[kp.slug] = kp

        created_roots = 0
        for slug, (name, order, difficulty) in NEW_CATEGORY_ROOTS.items():
            if slug in root_by_slug:
                # 已存在：仅更新元数据，不动 parent（根节点 parent 恒为 None）
                kp = root_by_slug[slug]
                kp.name = name
                kp.order = order
                kp.difficulty = difficulty
            else:
                kp = KnowledgePoint(
                    slug=slug,
                    name=name,
                    order=order,
                    difficulty=difficulty,
                    description=f"{name}根节点",
                )
                session.add(kp)
                await session.flush()
                root_by_slug[slug] = kp
                created_roots += 1
        await session.flush()

        # 2) 迁移知识点 parent_id
        target_slugs = list(REALLOCATE_MAP.keys())
        kps = (
            (await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug.in_(target_slugs)))).scalars().all()
        )

        moved = 0
        skipped = 0
        missing: list[str] = []
        for kp in kps:
            target_root_slug = REALLOCATE_MAP.get(kp.slug)
            if target_root_slug is None:
                continue
            target_root = root_by_slug.get(target_root_slug)
            if target_root is None:
                missing.append(f"{kp.slug} → {target_root_slug} (根节点不存在)")
                continue
            if kp.parent_id == target_root.id:
                skipped += 1
                continue
            kp.parent_id = target_root.id
            moved += 1

        # 检查映射中不存在的 slug
        found_slugs = {kp.slug for kp in kps}
        for slug in target_slugs:
            if slug not in found_slugs:
                missing.append(f"{slug} (知识点不存在)")

        await session.commit()

        # 3) 输出报告
        print(f"新建分类根节点: {created_roots}")
        print(f"迁移知识点: {moved}")
        print(f"已就位跳过: {skipped}")
        if missing:
            print("⚠️ 未处理:")
            for m in missing:
                print(f"  {m}")
        else:
            print("全部处理完成，无遗漏。")


if __name__ == "__main__":
    asyncio.run(main())
