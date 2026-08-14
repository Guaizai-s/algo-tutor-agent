"""清理 demo-*（验证）知识点：迁移题目关联到正式知识点后删除。

背景：P0-2 功能验证时创建的 10 个 demo-*（验证）知识点为临时节点，
正式知识体系已包含大部分对应节点；缺失的 4 个基础节点由本脚本幂等补齐。
本脚本：
1. 给正式 BFS 节点设置 cf_tag（承接 CF 'dfs and similar' 标签映射）
2. 重跑 CF 标签→知识点映射（全量幂等 upsert）
3. 把 14 道验证/诊断题的知识点关联迁移到正式节点
4. 删除 10 个 demo-* 节点（含其讲义、前置依赖、题目关联）

幂等：已迁移/已删除的行自动跳过。可重复执行。

用法（backend 容器内，data 挂载于 /data）：
    docker compose exec backend python -m scripts.migrate_demo_to_official
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint, KnowledgePointDifficulty, KnowledgePrerequisite, Lecture
from app.models.problem import Problem, ProblemKnowledgePoint
from app.services.codeforces.sync import sync_cf_tag_knowledge_mappings

# demo 节点 → 正式节点（承接 CF 标签映射的 slug）
DEMO_TO_OFFICIAL_CF: dict[str, str] = {
    "demo-array-hash": "sub-数据结构-基础数据结构",
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
    "demo-two-sum": "sub-数据结构-基础数据结构",
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

# 历史快照没有这四个正式节点。内置最小定义可以在缺少外部 enriched_index.json
# 的生产/开发环境中安全补齐；后续 seed_knowledge_graph 仍可丰富讲义与模板。
MISSING_OFFICIAL_SPECS: dict[str, tuple[str, str, str, int]] = {
    "oi-binary-search": ("二分查找", "在单调或有序空间中每次排除一半候选答案", "binary search", 20),
    "oi-greedy": ("贪心", "通过局部最优选择构造全局最优解", "greedy", 30),
    "oi-sorting": ("排序", "按关键字重排数据，为二分、双指针和贪心提供基础", "sortings", 10),
    "oi-two-pointers": ("双指针", "使用两个位置协同扫描以减少重复枚举", "two pointers", 40),
}

OFFICIAL_PARENT_SLUG = "sub-基础-基础算法"


async def ensure_missing_official_nodes(session) -> int:
    parent = (
        await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == OFFICIAL_PARENT_SLUG))
    ).scalar_one_or_none()
    if parent is None:
        raise RuntimeError(f"正式父知识点不存在: {OFFICIAL_PARENT_SLUG}")

    created = 0
    for slug, (name, description, cf_tag, order) in MISSING_OFFICIAL_SPECS.items():
        existing = (
            await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            KnowledgePoint(
                slug=slug,
                name=name,
                description=description,
                difficulty=KnowledgePointDifficulty.EASY,
                parent_id=parent.id,
                order=order,
                cf_tag=cf_tag,
            )
        )
        created += 1
    await session.flush()
    return created


async def migrate_demo_references(session, demo_id, official_id) -> None:
    """Move every known knowledge FK before deleting one demo node.

    Tables with a user/knowledge unique constraint need an explicit merge
    before the remaining rows can be updated.  Other references are direct
    updates.  This keeps mastery, paths, reviews, tasks, discussions, lecture
    reads, and notification context intact.
    """

    params = {"demo_id": demo_id, "official_id": official_id}

    statements = (
        # Replacing either side of an edge can collapse two demo nodes into
        # the same official node. Remove those edges before the UPDATEs so the
        # database-level not-self constraint is never violated.
        """
        DELETE FROM knowledge_prerequisites
        WHERE (knowledge_id = :demo_id AND prerequisite_id = :demo_id)
           OR (knowledge_id = :demo_id AND prerequisite_id = :official_id)
           OR (knowledge_id = :official_id AND prerequisite_id = :demo_id)
        """,
        """
        UPDATE user_knowledge_states target
            SET mastery = GREATEST(target.mastery, source.mastery),
                is_weak = target.is_weak OR source.is_weak,
                consecutive_wa = GREATEST(target.consecutive_wa, source.consecutive_wa),
                updated_at = GREATEST(target.updated_at, source.updated_at)
            FROM user_knowledge_states source
            WHERE target.user_id = source.user_id
              AND target.knowledge_id = :official_id
              AND source.knowledge_id = :demo_id
        """,
        """
        DELETE FROM user_knowledge_states source
            USING user_knowledge_states target
            WHERE source.user_id = target.user_id
              AND source.knowledge_id = :demo_id
              AND target.knowledge_id = :official_id
        """,
        "UPDATE user_knowledge_states SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        """
        UPDATE review_records target
            SET review_count = GREATEST(target.review_count, source.review_count),
                last_reviewed_at = GREATEST(target.last_reviewed_at, source.last_reviewed_at),
                next_review_at = LEAST(target.next_review_at, source.next_review_at),
                stage = CASE WHEN source.review_count > target.review_count THEN source.stage ELSE target.stage END,
                updated_at = GREATEST(target.updated_at, source.updated_at)
            FROM review_records source
            WHERE target.user_id = source.user_id
              AND target.knowledge_id = :official_id
              AND source.knowledge_id = :demo_id
        """,
        """
        DELETE FROM review_records source
            USING review_records target
            WHERE source.user_id = target.user_id
              AND source.knowledge_id = :demo_id
              AND target.knowledge_id = :official_id
        """,
        "UPDATE review_records SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        # The association table has a composite primary key.
        """
        DELETE FROM problem_knowledge_points source
            USING problem_knowledge_points target
            WHERE source.problem_id = target.problem_id
              AND source.knowledge_id = :demo_id
              AND target.knowledge_id = :official_id
        """,
        "UPDATE problem_knowledge_points SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE learning_path_items SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE daily_tasks SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE user_lecture_reads SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE discussions SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE notifications SET related_knowledge_id = :official_id WHERE related_knowledge_id = :demo_id",
        "UPDATE lectures SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE code_templates SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE knowledge_points SET parent_id = :official_id WHERE parent_id = :demo_id",
        "UPDATE knowledge_prerequisites SET knowledge_id = :official_id WHERE knowledge_id = :demo_id",
        "UPDATE knowledge_prerequisites SET prerequisite_id = :official_id WHERE prerequisite_id = :demo_id",
    )
    for statement in statements:
        await session.execute(text(statement), params)


async def remove_self_prerequisites(session) -> int:
    """Remove invalid historical self-edges left by older merge scripts."""
    result = await session.execute(
        delete(KnowledgePrerequisite).where(KnowledgePrerequisite.knowledge_id == KnowledgePrerequisite.prerequisite_id)
    )
    return result.rowcount or 0


async def main() -> None:
    async with async_session_maker() as session:
        # 0) 补齐历史快照缺失的正式基础节点，再校验全部目标。
        created_official = await ensure_missing_official_nodes(session)
        official_slugs = set(DEMO_TO_OFFICIAL_CF.values()) | set(PROBLEM_TO_OFFICIAL.values())
        existing = (
            (await session.execute(select(KnowledgePoint.slug).where(KnowledgePoint.slug.in_(official_slugs))))
            .scalars()
            .all()
        )
        missing_official = official_slugs - set(existing)
        if missing_official:
            raise RuntimeError(f"正式知识点缺失: {missing_official}")
        print(f"正式基础知识点补齐: +{created_official}")

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

        # 3) 迁移验证/诊断题的关联到正式节点
        demo_slugs = list(DEMO_TO_OFFICIAL_CF.keys())
        kp_rows = (
            await session.execute(
                select(KnowledgePoint.slug, KnowledgePoint.id).where(KnowledgePoint.slug.in_(demo_slugs))
            )
        ).all()
        demo_id_by_slug = {slug: kp_id for slug, kp_id in kp_rows}
        official_id_by_slug = dict(
            (
                await session.execute(
                    select(KnowledgePoint.slug, KnowledgePoint.id).where(KnowledgePoint.slug.in_(official_slugs))
                )
            ).all()
        )

        # 先迁移所有用户/内容引用，再处理题目语义映射。多个 demo 节点可汇入
        # 同一个正式节点，冲突行由 migrate_demo_references 合并。
        for demo_slug, official_slug in DEMO_TO_OFFICIAL_CF.items():
            demo_id = demo_id_by_slug.get(demo_slug)
            if demo_id is None:
                continue
            await migrate_demo_references(session, demo_id, official_id_by_slug[official_slug])

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
            demo_kp_ids = [v for v in demo_id_by_slug.values() if v is not None]
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
        removed_self_prerequisites = await remove_self_prerequisites(session)
        print(f"Removed historical self-prerequisites: {removed_self_prerequisites}")
        if not demo_ids:
            print("demo 节点已全部删除，跳过清理")
            await session.commit()
            print(f"迁移完成: CF 映射 +{mapped}, 题目迁移 {migrated}（幂等，无 demo 节点可删）")
            return

        # 引用和内容都已迁移，以下删除正常情况下不会再级联丢失业务数据。
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
