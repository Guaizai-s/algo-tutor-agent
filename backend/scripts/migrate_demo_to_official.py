"""清理 demo-*（验证）知识点：迁移题目关联到正式知识点后删除。

背景：P0-2 功能验证时创建的 9 个 demo-*（验证）知识点为临时节点，
正式知识体系已包含对应节点（缺失的 4 个由 seed_missing_basics 补灌）。
本脚本：
1. 给正式 BFS 节点设置 cf_tag（承接 CF 'dfs and similar' 标签映射）
2. 重跑 CF 标签→知识点映射（全量幂等 upsert）
3. 把 14 道验证/诊断题的知识点关联迁移到正式节点
4. 删除 9 个 demo-* 节点（含其讲义、前置依赖、题目关联）

幂等：已迁移/已删除的行自动跳过。可重复执行。

用法（backend 容器内，data 挂载于 /data）：
    docker compose exec backend python -m scripts.migrate_demo_to_official
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, KnowledgePrerequisite, Lecture
from app.models.problem import Problem, ProblemKnowledgePoint
from app.services.codeforces.sync import sync_cf_tag_knowledge_mappings

# demo 节点 → 正式节点（承接 CF 标签映射的 slug）
DEMO_TO_OFFICIAL_CF: dict[str, str] = {
    "demo-stack": "sub-数据结构-基础数据结构",
    "demo-binary-search": "oi-binary-search",
    "demo-sliding-window": "oi-two-pointers",
    "demo-dynamic-programming": "sub-动态规划-其他",
    "demo-graph-search": "oi-bfs",
    "demo-two-pointers": "oi-two-pointers",
    "demo-sorting": "oi-sorting",
    "demo-greedy": "oi-greedy",
    "demo-shortest-paths": "sub-图论-最短路",
}

# 验证/诊断题 → 正式知识点
PROBLEM_TO_OFFICIAL: dict[str, str] = {
    "demo-valid-parentheses": "oi-ds-stack",
    "demo-binary-search": "oi-binary-search",
    "demo-longest-substring": "oi-sliding-window",
    "demo-coin-change": "sub-动态规划-其他",
    "demo-number-of-islands": "oi-bfs",
    "demo-edit-distance": "sub-动态规划-其他",
    "demo-trapping-rain-water": "oi-two-pointers",
    "demo-sort-numbers": "oi-sorting",
    "demo-merge-sorted-arrays": "oi-two-pointers",
    "demo-interval-scheduling": "oi-greedy",
    "demo-grid-shortest-path": "sub-图论-最短路",
    "demo-topological-order": "oi-topo-sort",
    "demo-longest-increasing-subsequence": "sub-动态规划-其他",
    "demo-dijkstra": "sub-图论-最短路",
}

# oi-bfs 需设置 cf_tag 才能承接 CF 'dfs and similar' 标签的题
BFS_SLUG = "oi-bfs"
BFS_CF_TAG = "dfs and similar"


async def main() -> None:
    async with async_session_maker() as session:
        # 0) 正式节点是否存在（校验）
        official_slugs = set(DEMO_TO_OFFICIAL_CF.values()) | set(PROBLEM_TO_OFFICIAL.values())
        existing = (
            (await session.execute(select(KnowledgePoint.slug).where(KnowledgePoint.slug.in_(official_slugs))))
            .scalars()
            .all()
        )
        missing_official = official_slugs - set(existing)
        if missing_official:
            print(f"FATAL: 正式知识点缺失，先运行 seed_missing_basics: {missing_official}")
            return

        # 1) 给 BFS 设置 cf_tag（幂等）
        bfs_id = (
            await session.execute(select(KnowledgePoint.id).where(KnowledgePoint.slug == BFS_SLUG))
        ).scalar_one_or_none()
        if bfs_id is not None:
            res = await session.execute(
                update(KnowledgePoint).where(KnowledgePoint.id == bfs_id).values(cf_tag=BFS_CF_TAG)
            )
            print(f"oi-bfs 设置 cf_tag={BFS_CF_TAG!r} (rowcount={res.rowcount})")

        # 2) 重跑 CF 标签→知识点映射（幂等 upsert，CF 题挂到正式节点）
        mapped = await sync_cf_tag_knowledge_mappings(session)

        # 3) 迁移 14 道验证/诊断题的关联到正式节点
        demo_slugs = list(DEMO_TO_OFFICIAL_CF.keys())
        kp_rows = (
            await session.execute(
                select(KnowledgePoint.slug, KnowledgePoint.id).where(KnowledgePoint.slug.in_(demo_slugs))
            )
        ).all()
        demo_id_by_slug = {slug: kp_id for slug, kp_id in kp_rows}
        migrated = 0
        for p_slug, o_slug in PROBLEM_TO_OFFICIAL.items():
            pid = (await session.execute(select(Problem.id).where(Problem.slug == p_slug))).scalar_one_or_none()
            if pid is None:
                print(f"  SKIP 题不存在: {p_slug}")
                continue
            oid = (
                await session.execute(select(KnowledgePoint.id).where(KnowledgePoint.slug == o_slug))
            ).scalar_one_or_none()
            # 删除该题挂在 demo 节点上的旧关联
            demo_kp_ids = [v for k, v in demo_id_by_slug.items() if v is not None]
            if demo_kp_ids:
                await session.execute(
                    delete(ProblemKnowledgePoint).where(
                        ProblemKnowledgePoint.problem_id == pid,
                        ProblemKnowledgePoint.knowledge_id.in_(demo_kp_ids),
                    )
                )
            # 挂到正式节点（防重复）
            await session.execute(
                pg_insert(ProblemKnowledgePoint)
                .values(problem_id=pid, knowledge_id=oid)
                .on_conflict_do_nothing(index_elements=["problem_id", "knowledge_id"])
            )
            migrated += 1

        # 4) 删除 demo 节点（先子表后父表）
        demo_ids = [v for v in demo_id_by_slug.values() if v is not None]
        if not demo_ids:
            print("demo 节点已全部删除，跳过清理")
            await session.commit()
            print(f"迁移完成: CF 映射 +{mapped}, 题目迁移 {migrated}（幂等，无 demo 节点可删）")
            return

        await session.execute(delete(Lecture).where(Lecture.knowledge_id.in_(demo_ids)))
        await session.execute(
            delete(KnowledgePrerequisite).where(
                (KnowledgePrerequisite.knowledge_id.in_(demo_ids))
                | (KnowledgePrerequisite.prerequisite_id.in_(demo_ids))
            )
        )
        await session.execute(delete(ProblemKnowledgePoint).where(ProblemKnowledgePoint.knowledge_id.in_(demo_ids)))
        res = await session.execute(delete(KnowledgePoint).where(KnowledgePoint.id.in_(demo_ids)))
        await session.commit()

        print(f"清理完成: CF 映射 +{mapped}, 题目迁移 {migrated}, " f"删除 demo 节点 {res.rowcount}")


if __name__ == "__main__":
    asyncio.run(main())
