"""整理知识点一级分类：新增「入门」分类并归位错位知识点。

问题背景：
  之前 seed/merge 把大量本不属于「基础」的知识点塞进了 cat-基础，
  包括 10 个搜索类、6 个竞赛类、1 个数学符号表、6 个入门级知识点。
  这导致 Progress 页面「基础」分组混入无关内容，KnowledgeTree 分类语义混乱。

本次整理：
  1. 新建 3 个一级分类根节点：入门(-1000)、搜索(5000)、竞赛(11000)
  2. 把最基础的 6 个算法入门知识点从「基础」迁到「入门」
  3. 把错位的搜索类(10)迁到「搜索」、竞赛类(6)迁到「竞赛」、数学符号表迁到「数学」
  4. 「基础」仅保留：基础算法(含差分)、均摊复杂度、构造

迁移只改 parent_id，不影响题目关联 / 讲义 / 掌握度（均按 knowledge_id 关联）。

运行方式：
    docker compose exec backend python -m scripts.reorganize_categories

幂等：重复运行不会产生副作用，已归位的知识点保持不变。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, KnowledgePointDifficulty

# 新建的一级分类根节点配置：slug → (name, order, difficulty)
NEW_CATEGORY_ROOTS: dict[str, tuple[str, int, KnowledgePointDifficulty]] = {
    "cat-入门": ("入门分类", -1000, KnowledgePointDifficulty.EASY),
    "cat-搜索": ("搜索分类", 5000, KnowledgePointDifficulty.MEDIUM),
    "cat-竞赛": ("竞赛分类", 11000, KnowledgePointDifficulty.HARD),
}

# 已有的一级分类根节点 slug（用于数学符号表归位）
MATH_ROOT_SLUG = "cat-数学"

# 知识点 slug → 目标一级分类 slug（parent 归位映射）
# 仅列出需要迁移的；未列出的保持原 parent 不变
REALLOCATE_MAP: dict[str, str] = {
    # —— 入门：最基础的算法起步知识点 ——
    "oi-basic-complexity": "cat-入门",
    "oi-basic-enumerate": "cat-入门",
    "oi-basic-simulate": "cat-入门",
    "oi-basic-divide-and-conquer": "cat-入门",
    "oi-prefix-sum": "cat-入门",
    "oi-sliding-window": "cat-入门",
    # —— 搜索：从基础归位 ——
    "oi-search-alpha-beta": "cat-搜索",
    "oi-search-astar": "cat-搜索",
    "oi-search-backtracking": "cat-搜索",
    "oi-bfs": "cat-搜索",
    "oi-search-bidirectional": "cat-搜索",
    "oi-search-dlx": "cat-搜索",
    "oi-search-heuristic": "cat-搜索",
    "oi-search-idastar": "cat-搜索",
    "oi-search-iterative": "cat-搜索",
    "oi-search-opt": "cat-搜索",
    # —— 竞赛：从基础归位 ——
    "oi-contest-common-mistakes": "cat-竞赛",
    "oi-contest-common-tricks": "cat-竞赛",
    "oi-contest-dictionary": "cat-竞赛",
    "oi-contest-interaction": "cat-竞赛",
    "oi-contest-io": "cat-竞赛",
    "oi-contest-problems": "cat-竞赛",
    # —— 数学符号表：从基础归位到数学 ——
    "oi-intro-symbol": MATH_ROOT_SLUG,
}


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
