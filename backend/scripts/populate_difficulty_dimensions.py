"""填充知识点双维度难度评价初始值（comprehension_difficulty + theory_depth）。

设计原则：
- comprehension_difficulty (理解难度 1-5)：掌握该知识点本身有多难
- theory_depth (理论深度 1-5)：所需前置知识的进阶程度 / 依赖链长度

示例：
- 滑动窗口：理解难度=2（滑动概念直观），理论深度=1（几乎无前置）
- 二维差分：理解难度=2（与一维差分相近），理论深度=3（依赖一维差分+矩阵）
- 线段树：理解难度=3（区间操作需要一定抽象），理论深度=3（依赖递归+分治）
- FFT：理解难度=5，理论深度=5

运行方式：
    docker compose exec backend python -m scripts.populate_difficulty_dimensions

幂等：已有非默认值的知识点不会被覆盖。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text, update

from app.core.database import async_session_maker

# 按一级分类 slug（不含 cat- 前缀的根节点）的默认值
CATEGORY_DEFAULTS: dict[str, tuple[int, int]] = {
    "入门": (1, 1),
    "基础": (2, 1),
    "数据结构": (3, 2),
    "图论": (3, 2),
    "动态规划": (3, 3),
    "字符串": (2, 2),
    "搜索": (2, 2),
    "数学": (3, 2),
    "杂项": (2, 2),
    "竞赛": (4, 4),
}

# 基于 slug 关键词的精细调整：匹配到则 comprehension +dx, theory +dy
# 通过关键词识别难度特征，拉大区分度
SLUG_ADJUSTMENTS: list[tuple[list[str], int, int]] = [
    # —— 入门级 降低 ——
    (["intro", "basic", "concept", "save", "node", "overview"], 0, -1),
    # —— 进阶级 调高 ——
    (["divide", "persistent", "virtual", "centroid", "cdq"], 1, 2),
    (["opt", "slope", "quadrangle", "plug"], 1, 1),
    (["flow", "cut", "matching", "max", "min-cost", "min-cut"], 1, 2),
    (["tree", "hld", "lct", "splay", "treap", "scc", "bst"], 1, 1),
    (["fft", "ntt", "fwt", "poly", "berlekamp", "simplex"], 2, 2),
    (["game", "linear-program", "matroid"], 1, 1),
    (["number-theory-prime", "pollard", "meissel", "min-25", "discrete-log"], 2, 2),
    (["crt", "pell", "quad-residue", "primitive-root", "zhou"], 2, 2),
    (["automaton", "suffix", "sam", "pam", "lyndon"], 1, 2),
    (["geometry-3d", "half-plane", "triangulation", "convex-hull"], 1, 2),
    (["phantom", "preact"], 0, -1),
]

# 特定知识点的精细覆盖（slug → (comprehension, theory)）
# 基于知识点语义手动调整
SPECIFIC_OVERRIDES: dict[str, tuple[int, int]] = {
    # === 入门 ===
    "oi-basic-complexity": (1, 1),  # 复杂度简介：纯概念，无前置
    "oi-basic-enumerate": (1, 1),  # 枚举：暴力遍历，直观
    "oi-basic-simulate": (1, 1),  # 模拟：按题意实现，直观
    # === 基础 ===
    "sub-基础-基础算法": (2, 1),
    "oi-basic-amortized-analysis": (3, 1),  # 均摊复杂度：理解稍难，但无前置
    "oi-basic-construction": (3, 2),  # 构造：需要一定创造性思维
    "oi-difference": (2, 2),  # 差分：与一维相近，前置是前缀和
    # 入门从基础分离出来的
    "oi-basic-divide-and-conquer": (2, 1),  # 递归分治：概念直观
    "oi-prefix-sum": (2, 1),  # 前缀和：简单预处理
    "oi-sliding-window": (2, 1),  # 滑动窗口：双指针延伸
    # === 数据结构 ===
    "oi-ds-array": (1, 1),  # 数组：最基础结构
    "oi-linked-list": (1, 1),  # 链表
    "oi-stack": (1, 1),  # 栈
    "oi-queue": (1, 1),  # 队列
    "oi-heap": (2, 1),  # 堆：稍抽象但仍直观
    "oi-hash-table": (2, 1),  # 哈希表
    "oi-fenwick-tree": (3, 2),  # 树状数组：区间操作需要一定理解
    "oi-seg-tree": (3, 3),  # 线段树：区间操作抽象度高
    "oi-dsu": (2, 1),  # 并查集：路径压缩直观
    "oi-trie": (2, 2),  # Trie：前缀树，概念中等
    # === 图论 ===
    "oi-dfs": (2, 1),  # DFS：基础遍历
    "oi-bfs": (2, 1),  # BFS：基础遍历
    "oi-graph": (2, 1),  # 图基础概念
    "oi-shortest-path": (3, 2),  # 最短路：Dijkstra/Floyd 需要理解
    "oi-mst": (3, 2),  # 最小生成树
    "oi-topo-sort": (2, 2),  # 拓扑排序
    "oi-lca": (3, 2),  # LCA：需要倍增/树上结构
    "oi-scc": (4, 3),  # 强连通分量：Tarjan 算法较难
    "oi-max-flow": (4, 4),  # 网络流：理论深度高
    "oi-hld": (4, 3),  # 树链剖分
    "oi-cut-vertex": (3, 2),  # 割点
    "oi-bridge": (3, 2),  # 割边
    # === 动态规划 ===
    "oi-dp": (3, 2),  # DP 基础：概念中等
    "oi-knapsack-dp": (2, 2),  # 背包 DP：经典模型，易学
    "oi-bitmask-dp": (4, 3),  # 状压 DP：需要位运算+DP 基础
    "oi-interval-dp": (3, 3),  # 区间 DP
    "oi-tree-dp": (4, 3),  # 树形 DP：树+DP 组合
    "oi-digit-dp": (4, 4),  # 数位 DP
    # === 字符串 ===
    "oi-kmp": (3, 2),  # KMP：前缀函数较抽象
    "oi-string-hash": (2, 1),  # 字符串哈希：直观
    "oi-ac-automaton": (4, 3),  # AC 自动机：Trie+KMP 组合
    "oi-manacher": (3, 2),  # Manacher
    # === 搜索 ===
    "oi-search-alpha-beta": (4, 3),  # Alpha-Beta 剪枝
    "oi-search-astar": (4, 3),  # A*
    "oi-search-backtracking": (2, 2),  # 回溯法
    "oi-search-bidirectional": (3, 2),  # 双向搜索
    "oi-search-dlx": (4, 4),  # Dancing Links
    "oi-search-heuristic": (3, 3),  # 启发式搜索
    "oi-search-idastar": (4, 3),  # IDA*
    "oi-search-iterative": (3, 2),  # 迭代加深
    "oi-search-opt": (3, 3),  # 搜索优化
    # === 数学 ===
    "oi-binary-search": (2, 1),  # 二分查找：直观
    "oi-sorting": (2, 1),  # 排序
    "oi-greedy": (2, 1),  # 贪心
    "oi-prime": (2, 1),  # 质数
    "oi-gcd": (2, 1),  # GCD
    "oi-quick-pow": (2, 1),  # 快速幂
    "oi-crt": (4, 3),  # 中国剩余定理
    "oi-ftt": (5, 5),  # FFT 极其复杂
    "oi-game-theory": (3, 2),  # 博弈论
    "oi-catalan": (3, 2),  # 卡特兰数
    "oi-inclusion-exclusion": (3, 2),  # 容斥原理
    "oi-combinatorics": (3, 2),  # 组合数学
    "oi-number-theory": (3, 2),  # 数论基础
    "oi-matrix": (3, 2),  # 线性代数
    "oi-probability": (2, 2),  # 概率与统计
    # === 杂项 ===
    "oi-sqrt-decomposition": (3, 3),  # 分块
    "oi-mo-algorithm": (4, 3),  # 莫队
    "oi-binary-lifting": (3, 2),  # 倍增
    "oi-sparse-table": (2, 2),  # ST 表
    "oi-persistent": (4, 4),  # 可持久化数据结构
    "oi-virtual-tree": (4, 4),  # 虚树
    "oi-centroid-decomposition": (4, 4),  # 点分治
    "oi-cdq-divide": (4, 4),  # CDQ 分治
    "oi-parallel-binary": (4, 3),  # 整体二分
    "oi-simulated-annealing": (3, 2),  # 模拟退火
    # === 竞赛 ===
    "oi-contest-common-mistakes": (1, 1),  # 常见错误：经验类
    "oi-contest-common-tricks": (2, 2),  # 常见技巧
    "oi-contest-dictionary": (2, 3),  # 分段打表
    "oi-contest-interaction": (3, 2),  # 交互题
    "oi-contest-io": (1, 1),  # 读入输出优化
    "oi-contest-problems": (1, 1),  # 题型概述
    # === subtag 节点 ===
    "sub-数学-代数与数系": (4, 3),
    "sub-数学-数论进阶": (4, 4),
    "sub-数学-数论基础": (3, 2),
    "sub-数学-概率与统计": (2, 2),
    "sub-数学-其他": (2, 2),
    "sub-数学-数值计算": (3, 2),
    "sub-数学-组合数学": (3, 2),
    "sub-数学-线性代数": (3, 2),
    "sub-数学-多项式": (4, 4),
    "sub-数学-博弈论": (3, 2),
}


def _apply_slug_adjustment(slug: str, base_comp: int, base_theory: int) -> tuple[int, int]:
    """基于 slug 关键词调整 difficulty + theory，拉大区分度"""
    comp_delta, theory_delta = 0, 0
    slug_lower = slug.lower()
    for keywords, dc, dt in SLUG_ADJUSTMENTS:
        for kw in keywords:
            if kw in slug_lower:
                comp_delta += dc
                theory_delta += dt
                break  # 每组匹配一次
    # clamp 不允许到 0 以下或超过 5
    comp = min(max(base_comp + comp_delta, 1), 5)
    theory = min(max(base_theory + theory_delta, 1), 5)
    return comp, theory


async def main() -> None:
    from app.models.knowledge import KnowledgePoint

    async with async_session_maker() as session:
        # 0) 临时清空所有值，以便重新计算
        await session.execute(update(KnowledgePoint).values(comprehension_difficulty=0, theory_depth=0))

        # 1) 按分类设置基准值（SQL 批量）
        for cat, (comp, theory) in CATEGORY_DEFAULTS.items():
            root_slug = f"cat-{cat}"
            # 根节点
            await session.execute(
                update(KnowledgePoint)
                .where(KnowledgePoint.slug == root_slug)
                .values(comprehension_difficulty=comp, theory_depth=theory)
            )
            # 子树（至多 4 层递归查找分类归属）
            await session.execute(
                text("""
                    WITH RECURSIVE subtree AS (
                        SELECT k.id, k.parent_id, 0 as depth
                        FROM knowledge_points k
                        JOIN knowledge_points root ON root.id = k.parent_id
                        WHERE root.slug = :root_slug
                        UNION ALL
                        SELECT k.id, k.parent_id, s.depth + 1
                        FROM subtree s
                        JOIN knowledge_points k ON k.parent_id = s.id
                        WHERE s.depth < 4
                    )
                    UPDATE knowledge_points k
                    SET comprehension_difficulty = :comp,
                        theory_depth = :theory
                    FROM subtree s
                    WHERE k.id = s.id
                """),
                {"comp": comp, "theory": theory, "root_slug": root_slug},
            )
        # CF 标签
        await session.execute(
            update(KnowledgePoint)
            .where(KnowledgePoint.slug == "cat-CF标签")
            .values(comprehension_difficulty=2, theory_depth=2)
        )
        await session.execute(
            text("""
                WITH RECURSIVE subtree AS (
                    SELECT k.id, k.parent_id, 0 as depth
                    FROM knowledge_points k
                    JOIN knowledge_points root ON root.id = k.parent_id
                    WHERE root.slug = 'cat-CF标签'
                    UNION ALL
                    SELECT k.id, k.parent_id, s.depth + 1
                    FROM subtree s
                    JOIN knowledge_points k ON k.parent_id = s.id
                    WHERE s.depth < 4
                )
                UPDATE knowledge_points k
                SET comprehension_difficulty = 2,
                    theory_depth = 2
                FROM subtree s
                WHERE k.id = s.id
            """)
        )

        # 2) 基于 slug 关键词精细调整（Python 逐条处理，补偿 SQL 批量缺乏的粒度）
        rows = await session.execute(
            text("""
                SELECT id, slug, comprehension_difficulty, theory_depth
                FROM knowledge_points
                WHERE comprehension_difficulty > 0
                ORDER BY id
            """)
        )
        updates: list[dict] = []
        for row in rows.mappings().all():
            base_comp = row["comprehension_difficulty"]
            base_theory = row["theory_depth"]
            comp, theory = _apply_slug_adjustment(row["slug"], base_comp, base_theory)
            if (comp, theory) != (base_comp, base_theory):
                updates.append({"id": row["id"], "comp": comp, "theory": theory})

        if updates:
            # batch update
            for item in updates:
                await session.execute(
                    text("""
                        UPDATE knowledge_points
                        SET comprehension_difficulty = :comp,
                            theory_depth = :theory
                        WHERE id = :id
                    """),
                    item,
                )

        # 3) 精细覆盖（必须以最终值写入为准）
        overridden = 0
        for slug, (comp, theory) in SPECIFIC_OVERRIDES.items():
            result = await session.execute(
                text("""
                    UPDATE knowledge_points
                    SET comprehension_difficulty = :comp,
                        theory_depth = :theory
                    WHERE slug = :slug
                """),
                {"comp": comp, "theory": theory, "slug": slug},
            )
            if result.rowcount:
                overridden += result.rowcount

        # 4) 最终钳位 & 兜底（未被任何规则覆盖的设为 2,1）
        await session.execute(
            text("""
                UPDATE knowledge_points
                SET comprehension_difficulty = 2,
                    theory_depth = 1
                WHERE comprehension_difficulty = 0
            """)
        )
        await session.execute(
            text("""
                UPDATE knowledge_points
                SET comprehension_difficulty = GREATEST(1, LEAST(5, comprehension_difficulty)),
                    theory_depth = GREATEST(1, LEAST(5, theory_depth))
            """)
        )

        await session.commit()

        # 5) 验证分布
        r = await session.execute(
            text("""
                SELECT comprehension_difficulty, theory_depth, COUNT(*)
                FROM knowledge_points
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
        )
        print("两维分布：(comp, theory) → count")
        for comp, theory, cnt in r.all():
            color_comp = ["", "红", "橙", "黄", "绿", "青"][comp]
            color_theory = ["", "红", "橙", "黄", "绿", "青"][theory]
            print(f"  ({comp},{theory}) → {color_comp}/{color_theory} × {cnt}")
        print(f"精细覆盖: {overridden} 行")


if __name__ == "__main__":
    asyncio.run(main())
