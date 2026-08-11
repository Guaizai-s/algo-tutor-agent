"""将"其他"子分类中的知识点重新归类到合理子分类，并删除空壳。

运行方式：
    docker compose exec backend python -m scripts.migrate_subtags --yes

幂等：已移动的不会重复处理。
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select, text

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, KnowledgePointDifficulty

# ── 一级分类 slug → 名称 ────────────────────────────────────────────────────
CAT_SLUGS: dict[str, str] = {
    "基础": "cat-基础",
    "数据结构": "cat-数据结构",
    "图论": "cat-图论",
    "动态规划": "cat-动态规划",
    "字符串": "cat-字符串",
    "数学": "cat-数学",
    "杂项": "cat-杂项",
}

# ── 新建 subtag 定义 ────────────────────────────────────────────────────────
# (slug, 名称, 描述, 父分类, 难度)
NEW_SUBTAGS: list[tuple[str, str, str, str, KnowledgePointDifficulty]] = [
    # 基础
    (
        "sub-基础-基础算法",
        "基础算法",
        "排序、二分、双指针、贪心、前缀和、差分、递归、分治等基础算法",
        "基础",
        KnowledgePointDifficulty.EASY,
    ),
    # 图论
    (
        "sub-图论-特殊图论",
        "特殊图论",
        "圆方树、弦图、支配树、斯坦纳树等特殊图结构",
        "图论",
        KnowledgePointDifficulty.HARD,
    ),
    (
        "sub-图论-图论计数",
        "图论组合计数",
        "矩阵树定理、LGV 引理等图论组合计数方法",
        "图论",
        KnowledgePointDifficulty.HARD,
    ),
    # 数学
    (
        "sub-数学-数论进阶",
        "数论进阶",
        "筛法、同余方程、离散对数、二次剩余等进阶数论",
        "数学",
        KnowledgePointDifficulty.HARD,
    ),
    (
        "sub-数学-概率与统计",
        "概率与统计",
        "概率基本概念、随机变量、条件概率等",
        "数学",
        KnowledgePointDifficulty.MEDIUM,
    ),
    (
        "sub-数学-代数与数系",
        "代数与数系",
        "群论、环论、域论、布尔代数、进制、数值系统等",
        "数学",
        KnowledgePointDifficulty.HARD,
    ),
]

# ── 节点移动映射： (源 slug, 目标 subtag slug) ──────────────────────────────
# 目标 subtag 可以是已有或新建的；脚本会自动查找或创建
MOVE_MAP: list[tuple[str, str]] = [
    # ── Phase 1: 倍增 ──
    ("oi-binary-lifting", "sub-图论-树论"),
    # ── Phase 2: 图论-其他 ──
    # → 树论
    ("oi-graph-tree-basic", "sub-图论-树论"),
    ("oi-graph-tree-center", "sub-图论-树论"),
    ("oi-tree-diameter", "sub-图论-树论"),
    ("oi-graph-tree-hash", "sub-图论-树论"),
    ("oi-graph-tree-random-walk", "sub-图论-树论"),
    ("oi-graph-prufer", "sub-图论-树论"),
    ("oi-graph-tree-ahu", "sub-图论-树论"),
    ("oi-dsu-on-tree", "sub-图论-树论"),
    # → 图基础
    ("oi-graph-save", "sub-图论-图基础"),
    ("oi-graph-concept", "sub-图论-图基础"),
    ("oi-graph-dag", "sub-图论-图基础"),
    ("oi-graph-connectivity", "sub-图论-图基础"),
    ("oi-graph-node", "sub-图论-图基础"),
    # → 特殊图论
    ("oi-block-forest", "sub-图论-特殊图论"),
    ("oi-graph-chord", "sub-图论-特殊图论"),
    ("oi-graph-dominator-tree", "sub-图论-特殊图论"),
    ("oi-graph-steiner-tree", "sub-图论-特殊图论"),
    ("oi-graph-color", "sub-图论-特殊图论"),
    ("oi-graph-max-clique", "sub-图论-特殊图论"),
    ("oi-graph-dmst", "sub-图论-特殊图论"),
    ("oi-graph-planar", "sub-图论-特殊图论"),
    ("oi-graph-stoer-wagner", "sub-图论-特殊图论"),
    # → 图论计数
    ("oi-graph-matrix-tree", "sub-图论-图论计数"),
    ("oi-graph-lgv", "sub-图论-图论计数"),
    ("oi-graph-rings-count", "sub-图论-图论计数"),
    ("oi-graph-graph-random-walk", "sub-图论-图论计数"),
    # → 最短路
    ("oi-graph-kth-path", "sub-图论-最短路"),
    ("oi-graph-min-cycle", "sub-图论-最短路"),
    # → 基础/基础算法（差分是基础算法，非图论）
    ("oi-difference", "sub-基础-基础算法"),
    # ── Phase 3: 数据结构-其他 ──
    # → 树结构
    ("oi-ds-aa-tree", "sub-数据结构-树结构"),
    ("oi-ds-cat-tree", "sub-数据结构-树结构"),
    ("oi-ds-huffman-tree", "sub-数据结构-树结构"),
    ("oi-ds-sbt", "sub-数据结构-树结构"),
    ("oi-ds-wblt", "sub-数据结构-树结构"),
    ("oi-ds-finger-tree", "sub-数据结构-树结构"),
    ("oi-leftist-tree", "sub-数据结构-树结构"),
    ("oi-sgt", "sub-数据结构-树结构"),
    # → 高级结构
    ("oi-ds-lct", "sub-数据结构-高级结构"),
    ("oi-ds-top-tree", "sub-数据结构-高级结构"),
    ("oi-ds-ett", "sub-数据结构-高级结构"),
    ("oi-ds-divide-combine", "sub-数据结构-高级结构"),
    ("oi-ds-dividing", "sub-数据结构-高级结构"),
    ("oi-ds-pq-tree", "sub-数据结构-高级结构"),
    ("oi-ds-kinetic-tournament-tree", "sub-数据结构-高级结构"),
    # → 分块与离线
    ("oi-ds-sqrt-tree", "sub-数据结构-分块与离线"),
    ("oi-ds-seg-beats", "sub-数据结构-分块与离线"),
    ("oi-cdq-divide", "sub-数据结构-分块与离线"),  # 从杂项移入
    # → 基础数据结构
    ("oi-hash-table", "sub-数据结构-基础数据结构"),
    ("oi-sparse-table", "sub-数据结构-基础数据结构"),
    # ── Phase 4: 数学-其他 ──
    # → 数论基础
    ("oi-gcd", "sub-数学-数论基础"),
    # → 数论进阶
    ("oi-math-number-theory-bezouts", "sub-数学-数论进阶"),
    ("oi-math-number-theory-congruence-equation", "sub-数学-数论进阶"),
    ("oi-math-number-theory-continued-fraction", "sub-数学-数论进阶"),
    ("oi-math-number-theory-discrete-logarithm", "sub-数学-数论进阶"),
    ("oi-math-number-theory-du", "sub-数学-数论进阶"),
    ("oi-math-number-theory-euclidean", "sub-数学-数论进阶"),
    ("oi-math-number-theory-factorial", "sub-数学-数论进阶"),
    ("oi-math-number-theory-lift-the-exponent", "sub-数学-数论进阶"),
    ("oi-math-number-theory-linear-equation", "sub-数学-数论进阶"),
    ("oi-math-number-theory-lucas", "sub-数学-数论进阶"),
    ("oi-math-number-theory-meissel-lehmer", "sub-数学-数论进阶"),
    ("oi-math-number-theory-min-25", "sub-数学-数论进阶"),
    ("oi-math-number-theory-mod-arithmetic", "sub-数学-数论进阶"),
    ("oi-math-number-theory-pell-equation", "sub-数学-数论进阶"),
    ("oi-math-number-theory-pollard-rho", "sub-数学-数论进阶"),
    ("oi-math-number-theory-powerful-number", "sub-数学-数论进阶"),
    ("oi-math-number-theory-primitive-root", "sub-数学-数论进阶"),
    ("oi-math-number-theory-quadratic", "sub-数学-数论进阶"),
    ("oi-math-number-theory-quad-residue", "sub-数学-数论进阶"),
    ("oi-math-number-theory-residue", "sub-数学-数论进阶"),
    ("oi-math-number-theory-sieve", "sub-数学-数论进阶"),
    ("oi-math-number-theory-stern-brocot", "sub-数学-数论进阶"),
    ("oi-math-number-theory-zhou", "sub-数学-数论进阶"),
    # → 概率与统计
    ("oi-math-probability-basic-conception", "sub-数学-概率与统计"),
    ("oi-math-probability-concentration-inequality", "sub-数学-概率与统计"),
    ("oi-math-probability-conditional-probability", "sub-数学-概率与统计"),
    ("oi-math-probability-random-variable", "sub-数学-概率与统计"),
    ("oi-math-probability-exp-var", "sub-数学-概率与统计"),
    # → 代数与数系
    ("oi-math-algebra-basic", "sub-数学-代数与数系"),
    ("oi-math-algebra-field-theory", "sub-数学-代数与数系"),
    ("oi-math-algebra-group-theory", "sub-数学-代数与数系"),
    ("oi-math-algebra-ring-theory", "sub-数学-代数与数系"),
    ("oi-math-boolean-algebra", "sub-数学-代数与数系"),
    ("oi-math-order-theory", "sub-数学-代数与数系"),
    ("oi-math-complex", "sub-数学-代数与数系"),
    ("oi-math-coordinate", "sub-数学-代数与数系"),
    ("oi-math-numeral-sys-base", "sub-数学-代数与数系"),
    ("oi-math-numeral-sys-gray-code", "sub-数学-代数与数系"),
    ("oi-math-numeral-sys-balanced-ternary", "sub-数学-代数与数系"),
    ("oi-math-numeral-sys-intro", "sub-数学-代数与数系"),
    ("oi-math-linear-programming", "sub-数学-代数与数系"),
    ("oi-math-simplex", "sub-数学-代数与数系"),
    ("oi-math-matroid", "sub-数学-代数与数系"),
    ("oi-math-bignum", "sub-数学-代数与数系"),
    ("oi-math-bit", "sub-数学-代数与数系"),
    ("oi-math-binary-set", "sub-数学-代数与数系"),
    ("oi-math-numerical-interp", "sub-数学-代数与数系"),
    ("oi-math-algebra-schreier-sims", "sub-数学-代数与数系"),
    ("oi-math-berlekamp-massey", "sub-数学-代数与数系"),
    ("oi-math-game-theory-zero-sum-game", "sub-数学-代数与数系"),
    # → 组合数学
    ("oi-math-combinatorics-bernoulli", "sub-数学-组合数学"),
    ("oi-math-combinatorics-entringer", "sub-数学-组合数学"),
    ("oi-math-combinatorics-eulerian", "sub-数学-组合数学"),
    ("oi-math-combinatorics-fibonacci", "sub-数学-组合数学"),
    ("oi-math-combinatorics-graph-enumeration", "sub-数学-组合数学"),
    ("oi-math-combinatorics-partition", "sub-数学-组合数学"),
    ("oi-math-combinatorics-polya", "sub-数学-组合数学"),
    # → 线性代数
    ("oi-math-linear-algebra-diagonalization", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-elementary-operations", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-jordan", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-linear-mapping", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-product", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-vector", "sub-数学-线性代数"),
    ("oi-math-linear-algebra-vector-space", "sub-数学-线性代数"),
    # → 多项式
    ("oi-math-poly-comp-rev", "sub-数学-多项式"),
    ("oi-math-poly-czt", "sub-数学-多项式"),
    ("oi-math-poly-egf", "sub-数学-多项式"),
    ("oi-math-poly-fft", "sub-数学-多项式"),
    ("oi-math-poly-fundamental", "sub-数学-多项式"),
    ("oi-math-poly-fwt", "sub-数学-多项式"),
    ("oi-math-poly-linear-recurrence", "sub-数学-多项式"),
    ("oi-math-poly-ntt", "sub-数学-多项式"),
    ("oi-math-poly-ogf", "sub-数学-多项式"),
    ("oi-math-poly-symbolic-method", "sub-数学-多项式"),
    # ── Phase 5: 字符串-其他 ──
    ("oi-string-bm", "sub-字符串-字符串匹配"),
    ("oi-string-lyndon", "sub-字符串-字符串匹配"),
    ("oi-string-minimal-string", "sub-字符串-字符串匹配"),
    ("oi-string-lib-func", "sub-字符串-字符串基础"),
    ("oi-string-suffix-bst", "sub-字符串-回文与数组"),
]

# ── 迁移后需删除的空壳 subtag ───────────────────────────────────────────────
EMPTY_SUBTAGS_TO_DELETE: list[str] = [
    "sub-基础-其他",
    "sub-字符串-其他",
    "sub-杂项-其他",
]


async def ensure_subtags(session) -> dict[str, KnowledgePoint]:
    """确保所有需要的 subtag 节点存在，返回 {slug: KnowledgePoint} 映射。
    新建 subtag 时会在对应的一级分类节点下创建。
    """
    # 先加载所有已有 subtag
    result = await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug.like("sub-%")))
    existing = {kp.slug: kp for kp in result.scalars().all()}

    # 加载所有分类节点（名称如 "图论分类"、"数据结构分类"）
    result = await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug.like("cat-%")))
    cats_raw = {kp.name: kp for kp in result.scalars().all()}
    # 同时支持 "图论" 和 "图论分类" 两种查找方式
    cats: dict[str, KnowledgePoint] = {}
    for name, kp in cats_raw.items():
        cats[name] = kp
        if name.endswith("分类"):
            cats[name[:-2]] = kp  # "图论分类" → "图论"

    for slug, name, desc, cat_name, difficulty in NEW_SUBTAGS:
        if slug in existing:
            continue
        cat = cats.get(cat_name)
        if cat is None:
            print(f"  [warn] 分类 '{cat_name}' 不存在，跳过新建 {slug}")
            continue
        kp = KnowledgePoint(
            id=uuid4(),
            name=name,
            slug=slug,
            description=desc,
            difficulty=difficulty,
            parent_id=cat.id,
            order=0,
        )
        session.add(kp)
        existing[slug] = kp
        print(f"  [create] {slug} ({name}) under {cat_name}")

    await session.flush()
    return existing


async def migrate_nodes(session, subtags: dict[str, KnowledgePoint]) -> dict[str, int]:
    """移动节点到目标 subtag。"""
    stats = {"moved": 0, "skipped": 0, "not_found": 0}

    for src_slug, target_slug in MOVE_MAP:
        src_kp = (
            await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == src_slug))
        ).scalar_one_or_none()

        if src_kp is None:
            stats["not_found"] += 1
            continue

        target = subtags.get(target_slug)
        if target is None:
            print(f"  [warn] 目标 subtag '{target_slug}' 不存在，跳过 {src_slug}")
            stats["skipped"] += 1
            continue

        if src_kp.parent_id == target.id:
            stats["skipped"] += 1
            continue

        src_kp.parent_id = target.id
        stats["moved"] += 1
        print(f"  [move] {src_slug} → {target_slug}")

    await session.flush()
    return stats


async def delete_empty_subtags(session) -> int:
    """删除没有子节点的 subtag（先清理关联的 code_templates）。"""
    from app.models.knowledge import CodeTemplate

    deleted = 0
    for slug in EMPTY_SUBTAGS_TO_DELETE:
        kp = (await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == slug))).scalar_one_or_none()
        if kp is None:
            continue

        # 检查是否还有子节点
        child_count = (
            await session.execute(
                text("SELECT COUNT(*) FROM knowledge_points WHERE parent_id = :pid"),
                {"pid": kp.id},
            )
        ).scalar()

        if child_count > 0:
            print(f"  [skip] {slug} 仍有 {child_count} 个子节点，不删除")
            continue

        # 删除关联的 code_templates（避免 NOT NULL 约束冲突）
        templates = (
            (await session.execute(select(CodeTemplate).where(CodeTemplate.knowledge_id == kp.id))).scalars().all()
        )
        for tpl in templates:
            await session.delete(tpl)
        await session.flush()

        # 删除关联的 lectures
        from app.models.knowledge import Lecture

        lectures = (await session.execute(select(Lecture).where(Lecture.knowledge_id == kp.id))).scalars().all()
        for lec in lectures:
            await session.delete(lec)
        await session.flush()

        await session.delete(kp)
        deleted += 1
        print(f"  [delete] {slug} (空壳)")

    await session.flush()
    return deleted


async def run_migration() -> dict[str, int]:
    stats = {"subtags_created": 0, "nodes_moved": 0, "nodes_skipped": 0, "nodes_not_found": 0, "empties_deleted": 0}

    async with async_session_maker() as session:
        print("1) 确保 subtag 节点存在...")
        subtags = await ensure_subtags(session)
        stats["subtags_created"] = len([s for s in NEW_SUBTAGS if s[0] in subtags])

        print("\n2) 移动节点...")
        move_stats = await migrate_nodes(session, subtags)
        stats["nodes_moved"] = move_stats["moved"]
        stats["nodes_skipped"] = move_stats["skipped"]
        stats["nodes_not_found"] = move_stats["not_found"]

        print("\n3) 删除空壳 subtag...")
        stats["empties_deleted"] = await delete_empty_subtags(session)

        await session.commit()

    return stats


async def main() -> None:
    import sys

    auto_yes = "--yes" in sys.argv or "-y" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print("=== 知识点子分类清洗 ===\n")
    print(f"  将移动: {len(MOVE_MAP)} 个节点")
    print(f"  将新建: {len(NEW_SUBTAGS)} 个 subtag")
    print(f"  将删除: {len(EMPTY_SUBTAGS_TO_DELETE)} 个空壳")
    print()

    if dry_run:
        print("Dry run 模式，仅预览。")
        return

    if not auto_yes:
        print("使用 --yes 参数自动确认执行。")
        return

    print("执行中...\n")
    stats = await run_migration()

    print("\n完成:")
    print(f"  节点移动: {stats['nodes_moved']}")
    print(f"  节点跳过: {stats['nodes_skipped']}")
    print(f"  节点未找到: {stats['nodes_not_found']}")
    print(f"  空壳删除: {stats['empties_deleted']}")


if __name__ == "__main__":
    asyncio.run(main())
