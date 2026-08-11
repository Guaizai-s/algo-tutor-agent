"""合并重复知识点：将非规范 slug 的知识点合并到规范 slug 下。

运行方式：
    docker compose exec backend python -m scripts.merge_duplicate_kps

幂等：已合并的不会重复处理。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select, text

from app.core.database import async_session_maker
from app.models.knowledge import (
    CodeTemplate,
    KnowledgePoint,
    KnowledgePrerequisite,
    Lecture,
)

# 合并映射：重复 slug → 规范 slug
# 规范 slug 是 MERGE_KEYWORDS 中定义的 oi-xxx 格式
MERGE_MAP: dict[str, str] = {
    # DFS
    "oi-search-dfs": "oi-dfs",
    "oi-graph-dfs": "oi-dfs",
    # BFS
    "oi-search-bfs": "oi-bfs",
    "oi-graph-bfs": "oi-bfs",
    # LCA
    "oi-graph-lca": "oi-lca",
    # 替罪羊树
    "oi-ds-sgt": "oi-sgt",
    "zuo-150-有序表专题3-替罪羊树": "oi-sgt",
    # 树的直径
    "oi-graph-tree-diameter": "oi-tree-diameter",
    "zuo-121-树上问题专题4-树的直径": "oi-tree-diameter",
    # 树的重心
    "oi-graph-tree-centroid": "oi-tree-centroid",
    "zuo-120-树上问题专题3-树的重心": "oi-tree-centroid",
    # 卡特兰数
    "oi-math-combinatorics-catalan": "oi-catalan",
    "zuo-147-卡特兰数题型详解和取模处理": "oi-catalan",
    # 圆方树
    "oi-graph-block-forest": "oi-block-forest",
    "zuo-194-圆方树的原理和相关题目": "oi-block-forest",
    # 树上启发式合并
    "oi-graph-dsu-on-tree": "oi-dsu-on-tree",
    "zuo-163-树上启发式合并的原理和相关题目": "oi-dsu-on-tree",
    # 分数规划
    "oi-misc-frac-programming": "oi-frac-programming",
    "zuo-138-01分数规划": "oi-frac-programming",
    # 博弈论
    "oi-math-game-theory-intro": "oi-game-theory",
    # 容斥原理
    "oi-math-combinatorics-inclusion-exclusion-principle": "oi-inclusion-exclusion",
    # 哈希表
    "oi-ds-hash": "oi-hash-table",
    "zuo-026-哈希表-有序表和比较器的用法": "oi-hash-table",
    "zuo-106-哈希函数-哈希表-布隆过滤器-一致性哈希": "oi-hash-table",
    # 上/下（左程云博弈论章节，应合并到博弈论）
    "zuo-095-博弈类问题必备内容详解-上": "oi-game-theory",
    "zuo-096-博弈类问题必备内容详解-下": "oi-game-theory",
    # 叶子节点合并到同名 subtag 节点（消除"区间DP（动态规划）+ 区间DP"冗余）
    "oi-interval-dp": "sub-动态规划-区间-DP",
    "oi-game-theory": "sub-数学-博弈论",
    "oi-string-match": "sub-字符串-字符串匹配",
    "oi-string-hash": "sub-字符串-字符串哈希",
    "oi-string-basic": "sub-字符串-字符串基础",
    "oi-digit-dp": "sub-动态规划-数位-DP",
    "oi-math-number-theory-basic": "sub-数学-数论基础",
    "oi-shortest-path": "sub-图论-最短路",
    "oi-tree-dp": "sub-动态规划-树形-DP",
    "oi-combinatorics": "sub-数学-组合数学",
    "oi-max-flow": "sub-图论-网络流",
    "oi-knapsack-dp": "sub-动态规划-背包-DP",
    # 图匹配
    "oi-graph-graph-matching-graph-match": "oi-graph-matching",
    # 矩阵（OI-wiki 和 CF tag 合并）
    "oi-math-linear-algebra-matrix": "oi-matrix",
    # 上/下（左程云子数组问题章节，合并到前缀和）
    "zuo-070-子数组最大累加和问题与扩展-上": "oi-prefix-sum",
    "zuo-071-子数组最大累加和问题与扩展-下": "oi-prefix-sum",
    # 左偏树
    "oi-leftist-tree": "oi-leftist-tree",  # 已是规范 slug，不需要合并
    # ST 表
    "oi-sparse-table": "oi-sparse-table",  # 已是规范 slug
    # 分块与离线（杂项）合并到数据结构的分块与离线
    "sub-杂项-分块与离线": "sub-数据结构-分块与离线",
    # --- CF 标签合并到已有分类/subtag（"不用分CF和OI-wiki标签，意思一样直接合并"）---
    # 类别级概念 → 合并到分类根
    "oi-dp": "sub-动态规划-其他",  # 动态规划
    "oi-graph": "sub-图论-图基础",  # 图论
    "oi-data-structures": "sub-数据结构-基础数据结构",  # 数据结构
    "oi-math": "sub-数学-数论基础",  # 数学
    "oi-string": "sub-字符串-字符串基础",  # 字符串
    "oi-tree": "sub-数据结构-树结构",  # 树
    "oi-geometry": "sub-数学-代数与数系",  # 计算几何
    "oi-number-theory": "sub-数学-数论基础",  # 数论
    "oi-probability": "sub-数学-概率与统计",  # 概率
    "oi-constructive": "sub-基础-基础算法",  # 构造算法
    # 具体概念 → 合并到对应 subtag
    "oi-dfs": "sub-图论-图基础",  # DFS 深度优先搜索
    "oi-greedy": "sub-基础-基础算法",  # 贪心
    "oi-binary-search": "sub-基础-基础算法",  # 二分查找
    "oi-dsu": "sub-数据结构-基础数据结构",  # 并查集
    "oi-bitmask-dp": "sub-动态规划-状压-DP",  # 状态压缩 DP
    "oi-two-pointers": "sub-基础-基础算法",  # 双指针
    "oi-sorting": "sub-基础-基础算法",  # 排序
    "oi-divide-conquer": "sub-基础-基础算法",  # 分治
    "oi-ternary-search": "sub-基础-基础算法",  # 三分查找
    "oi-brute-force": "sub-基础-基础算法",  # 暴力枚举
    "oi-meet-in-middle": "sub-基础-基础算法",  # 折半搜索
    "oi-fft": "sub-数学-多项式",  # FFT
    "oi-suffix-structure": "sub-字符串-字符串匹配",  # 后缀结构
    "oi-crt": "sub-数学-数论基础",  # 中国剩余定理
    "oi-2-sat": "sub-图论-连通性",  # 2-SAT
    "oi-graph-matching": "sub-图论-图基础",  # 图匹配
    "oi-matrix": "sub-数学-线性代数",  # 矩阵
}


async def merge_duplicates(dry_run: bool = False) -> dict[str, int]:
    """合并重复知识点，返回统计信息。"""
    stats = {
        "merged": 0,
        "lectures_moved": 0,
        "templates_moved": 0,
        "prerequisites_fixed": 0,
        "problem_links_moved": 0,
        "skipped": 0,
    }

    async with async_session_maker() as session:
        for dup_slug, canon_slug in MERGE_MAP.items():
            if dup_slug == canon_slug:
                continue

            # 查找重复知识点和规范知识点
            dup_kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == dup_slug))
            ).scalar_one_or_none()

            canon_kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == canon_slug))
            ).scalar_one_or_none()

            if dup_kp is None:
                stats["skipped"] += 1
                continue

            if canon_kp is None:
                # 规范知识点不存在，将重复知识点重命名为规范 slug
                print(f"  [rename] {dup_slug} → {canon_slug} (canonical not found, renaming)")
                dup_kp.slug = canon_slug
                stats["merged"] += 1
                continue

            if dup_kp.id == canon_kp.id:
                continue

            print(f"  [merge] {dup_slug} (id={dup_kp.id}) → {canon_slug} (id={canon_kp.id})")

            if dry_run:
                stats["merged"] += 1
                continue

            # 1) 移动 Lecture
            dup_lectures = (
                (await session.execute(select(Lecture).where(Lecture.knowledge_id == dup_kp.id))).scalars().all()
            )
            for lec in dup_lectures:
                # 检查规范知识点是否已有同名讲义
                existing = (
                    await session.execute(
                        select(Lecture).where(
                            Lecture.knowledge_id == canon_kp.id,
                            Lecture.title == lec.title,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    lec.knowledge_id = canon_kp.id
                    stats["lectures_moved"] += 1
                else:
                    # 同名讲义已存在，删除重复的
                    await session.delete(lec)
            await session.flush()

            # 2) 移动 CodeTemplate
            dup_templates = (
                (await session.execute(select(CodeTemplate).where(CodeTemplate.knowledge_id == dup_kp.id)))
                .scalars()
                .all()
            )
            for tpl in dup_templates:
                tpl.knowledge_id = canon_kp.id
                stats["templates_moved"] += 1
            await session.flush()

            # 3) 修复 KnowledgePrerequisite（把引用 dup_kp 的改为引用 canon_kp）
            # 3a) 作为 knowledge_id（子节点）
            dup_as_child = (
                (
                    await session.execute(
                        select(KnowledgePrerequisite).where(KnowledgePrerequisite.knowledge_id == dup_kp.id)
                    )
                )
                .scalars()
                .all()
            )
            for pr in dup_as_child:
                # 检查是否已存在相同关系
                existing = (
                    await session.execute(
                        select(KnowledgePrerequisite).where(
                            KnowledgePrerequisite.knowledge_id == canon_kp.id,
                            KnowledgePrerequisite.prerequisite_id == pr.prerequisite_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    pr.knowledge_id = canon_kp.id
                    stats["prerequisites_fixed"] += 1
                else:
                    await session.delete(pr)
            await session.flush()

            # 3b) 作为 prerequisite_id（父节点）
            dup_as_parent = (
                (
                    await session.execute(
                        select(KnowledgePrerequisite).where(KnowledgePrerequisite.prerequisite_id == dup_kp.id)
                    )
                )
                .scalars()
                .all()
            )
            for pr in dup_as_parent:
                existing = (
                    await session.execute(
                        select(KnowledgePrerequisite).where(
                            KnowledgePrerequisite.knowledge_id == pr.knowledge_id,
                            KnowledgePrerequisite.prerequisite_id == canon_kp.id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    pr.prerequisite_id = canon_kp.id
                    stats["prerequisites_fixed"] += 1
                else:
                    await session.delete(pr)
            await session.flush()

            # 4) 修复 problem_knowledge_points 关联
            # 先删除目标已存在的重复关联（同一问题同时关联 dup 和 canon），避免唯一约束冲突
            await session.execute(
                text(
                    "DELETE FROM problem_knowledge_points "
                    "WHERE knowledge_id = :canon_id "
                    "AND problem_id IN ("
                    "  SELECT problem_id FROM problem_knowledge_points "
                    "  WHERE knowledge_id = :dup_id"
                    ")"
                ),
                {"canon_id": canon_kp.id, "dup_id": dup_kp.id},
            )
            result = await session.execute(
                text("UPDATE problem_knowledge_points SET knowledge_id = :canon_id " "WHERE knowledge_id = :dup_id"),
                {"canon_id": canon_kp.id, "dup_id": dup_kp.id},
            )
            stats["problem_links_moved"] += result.rowcount or 0

            # 5) 修复子知识点的 parent_id
            result = await session.execute(
                text("UPDATE knowledge_points SET parent_id = :canon_id " "WHERE parent_id = :dup_id"),
                {"canon_id": canon_kp.id, "dup_id": dup_kp.id},
            )
            await session.flush()

            # 6) 合并 cf_tag 信息（如果规范节点没有 cf_tag 但重复节点有）
            if dup_kp.cf_tag and not canon_kp.cf_tag:
                canon_kp.cf_tag = dup_kp.cf_tag
                canon_kp.cf_problem_count = max(canon_kp.cf_problem_count or 0, dup_kp.cf_problem_count or 0)

            # 7) 删除重复知识点
            await session.delete(dup_kp)
            stats["merged"] += 1

        await session.commit()

    return stats


async def main() -> None:
    import sys

    auto_yes = "--yes" in sys.argv or "-y" in sys.argv
    dry_run_only = "--dry-run" in sys.argv

    print("=== 合并重复知识点 ===\n")

    if dry_run_only:
        print("Dry run 模式：仅检查，不实际修改")
        print("-" * 50)
        stats = await merge_duplicates(dry_run=True)
        print("\nDry run 结果:")
        print(f"  将合并: {stats['merged']}")
        print(f"  将跳过: {stats['skipped']}")
        if stats["merged"] == 0:
            print("\n没有需要合并的重复知识点。")
        return

    # 先 dry run 检查
    print("检查中...")
    stats = await merge_duplicates(dry_run=True)
    print(f"  将合并: {stats['merged']}")
    print(f"  将跳过: {stats['skipped']}")

    if stats["merged"] == 0:
        print("\n没有需要合并的重复知识点。")
        return

    if not auto_yes:
        print("\n使用 --yes 参数自动确认执行。")
        return

    print("\n执行合并...")
    stats = await merge_duplicates(dry_run=False)
    print("\n合并完成:")
    print(f"  已合并: {stats['merged']}")
    print(f"  已跳过: {stats['skipped']}")
    print(f"  已移动讲义: {stats['lectures_moved']}")
    print(f"  已移动模板: {stats['templates_moved']}")
    print(f"  已修复依赖: {stats['prerequisites_fixed']}")
    print(f"  已移动题目关联: {stats['problem_links_moved']}")


if __name__ == "__main__":
    asyncio.run(main())
