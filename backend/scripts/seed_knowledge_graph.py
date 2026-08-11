"""Seed the knowledge graph from external sources.

数据储存层：仅负责 DB upsert（knowledge_points / lectures / code_templates / prerequisites）。
分类清洗由 ``scripts._enrich_index`` 完成（预计算 enriched_index.json），
组装由 ``scripts._seed_data.build_specs`` 完成。

Run from the backend container (``./data`` is mounted at ``/data``):

    docker compose exec backend python -m scripts.seed_knowledge_graph

若 enriched_index.json 不存在，会自动运行 _enrich_index 生成。
Idempotent: existing rows are matched by slug and updated in place.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import (
    CodeTemplate,
    KnowledgePoint,
    KnowledgePrerequisite,
    Lecture,
)
from scripts._classification_config import (
    CATEGORY_ROOT_SLUG_PREFIX,
    PREREQUISITES,
)
from scripts._seed_data import (
    DATA_ROOT,
    KnowledgePointSpec,
    build_specs,
    load_enriched_index,
)

# ---------------- DB upsert ----------------


async def upsert_knowledge_tree(
    root_specs: list[KnowledgePointSpec],
    leaf_specs: list[KnowledgePointSpec],
    subtag_slug_map: dict[tuple[str, str], str],
) -> tuple[dict[str, KnowledgePoint], int]:
    """返回 (slug -> KnowledgePoint, 新建数)"""
    slug_to_kp: dict[str, KnowledgePoint] = {}
    created = 0

    async with async_session_maker() as session:
        # 1) 虚拟根（一级分类）
        for spec in root_specs:
            kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == spec.slug))
            ).scalar_one_or_none()
            if kp is None:
                kp = KnowledgePoint(slug=spec.slug, name=spec.name)
                session.add(kp)
                created += 1
            kp.name = spec.name
            kp.description = spec.description
            kp.difficulty = spec.difficulty
            kp.parent_id = None
            kp.order = spec.order
            slug_to_kp[spec.slug] = kp
        await session.flush()

        # 2) 叶子 + subtag 虚拟节点
        # 先处理 subtag 虚拟节点（is_subtag_node=True），它们挂到一级分类根下
        subtag_specs = [s for s in leaf_specs if s.is_subtag_node]
        real_leaves = [s for s in leaf_specs if not s.is_subtag_node]

        for spec in subtag_specs:
            kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == spec.slug))
            ).scalar_one_or_none()
            if kp is None:
                kp = KnowledgePoint(slug=spec.slug, name=spec.name)
                session.add(kp)
                created += 1
            kp.name = spec.name
            kp.description = spec.description
            kp.difficulty = spec.difficulty
            kp.order = spec.order
            parent = slug_to_kp.get(f"{CATEGORY_ROOT_SLUG_PREFIX}{spec.category}")
            kp.parent_id = parent.id if parent else None
            slug_to_kp[spec.slug] = kp
        await session.flush()

        # 3) 真实叶子：若 subtag 非空则挂到 subtag 节点，否则挂到一级分类根
        for spec in real_leaves:
            kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == spec.slug))
            ).scalar_one_or_none()
            if kp is None:
                kp = KnowledgePoint(slug=spec.slug, name=spec.name)
                session.add(kp)
                created += 1
            kp.name = spec.name
            kp.description = spec.description
            kp.difficulty = spec.difficulty
            kp.order = spec.order
            kp.cf_tag = spec.cf_tag
            kp.cf_problem_count = spec.cf_problem_count
            # 父节点：优先 subtag，其次一级分类根
            parent_slug: str | None = None
            if spec.subtag:
                parent_slug = subtag_slug_map.get((spec.category, spec.subtag))
            if not parent_slug:
                parent_slug = f"{CATEGORY_ROOT_SLUG_PREFIX}{spec.category}"
            parent = slug_to_kp.get(parent_slug)
            kp.parent_id = parent.id if parent else None
            slug_to_kp[spec.slug] = kp
        await session.commit()

    return slug_to_kp, created


async def upsert_lectures(
    leaf_specs: list[KnowledgePointSpec], slug_to_kp: dict[str, KnowledgePoint]
) -> tuple[int, int]:
    """幂等写入 Lecture。匹配键：(knowledge_id, title)。

    Lecture.source 字段在新建和更新时都写入：新建时按 spec 来源设置，已存在的讲义同步迁移
    （从默认值 oi_wiki 修正为正确来源），支持 rewrite_lectures.py 按 source 筛选原始讲义。

    返回 (created, updated)。
    """
    created = 0
    updated = 0
    async with async_session_maker() as session:
        for spec in leaf_specs:
            kp = slug_to_kp[spec.slug]
            for level, title, content, source in spec.lectures:
                lec = (
                    await session.execute(
                        select(Lecture).where(
                            Lecture.knowledge_id == kp.id,
                            Lecture.title == title,
                        )
                    )
                ).scalar_one_or_none()
                if lec is None:
                    lec = Lecture(
                        knowledge_id=kp.id,
                        level=level,
                        title=title,
                        content=content,
                        source=source,
                    )
                    session.add(lec)
                    created += 1
                else:
                    lec.level = level
                    lec.content = content
                    # 存量迁移：已存在的讲义也更新 source（之前默认为 oi_wiki）
                    lec.source = source
                    updated += 1
        await session.commit()
    return created, updated


async def upsert_code_templates(leaf_specs: list[KnowledgePointSpec], slug_to_kp: dict[str, KnowledgePoint]) -> int:
    """幂等写入 CodeTemplate。匹配键：(knowledge_id, language, template_code 前 200 字符 hash)"""
    created = 0
    async with async_session_maker() as session:
        for spec in leaf_specs:
            kp = slug_to_kp[spec.slug]
            # 查询已存在的该知识点所有模板，按 (language, code 前缀) 去重
            existing = (
                (await session.execute(select(CodeTemplate).where(CodeTemplate.knowledge_id == kp.id))).scalars().all()
            )
            existing_keys = {(t.language, t.template_code[:200]) for t in existing}
            for lang, code, explanation in spec.templates:
                key = (lang, code[:200])
                if key in existing_keys:
                    continue
                tpl = CodeTemplate(
                    knowledge_id=kp.id,
                    language=lang,
                    template_code=code,
                    explanation=explanation,
                )
                session.add(tpl)
                created += 1
                existing_keys.add(key)
        await session.commit()
    return created


async def upsert_prerequisites(slug_to_kp: dict[str, KnowledgePoint]) -> int:
    """写入知识点依赖关系到 knowledge_prerequisites 表。

    匹配键：(knowledge_id, prerequisite_id) 幂等。
    只写入两端都存在的知识点。
    """
    created = 0
    async with async_session_maker() as session:
        # 查询已存在的所有依赖关系，避免重复插入
        existing = (
            await session.execute(select(KnowledgePrerequisite.knowledge_id, KnowledgePrerequisite.prerequisite_id))
        ).all()
        existing_pairs = {(r[0], r[1]) for r in existing}

        for child_slug, parent_slugs in PREREQUISITES.items():
            child_kp = slug_to_kp.get(f"oi-{child_slug}")
            if child_kp is None:
                continue
            for parent_slug in parent_slugs:
                parent_kp = slug_to_kp.get(f"oi-{parent_slug}")
                if parent_kp is None:
                    continue
                if (child_kp.id, parent_kp.id) in existing_pairs:
                    continue
                rel = KnowledgePrerequisite(
                    knowledge_id=child_kp.id,
                    prerequisite_id=parent_kp.id,
                )
                session.add(rel)
                created += 1
                existing_pairs.add((child_kp.id, parent_kp.id))
        await session.commit()
    return created


# ---------------- main ----------------


async def main() -> None:
    # 若 enriched_index.json 不存在，自动运行 enrichment
    enriched_path = DATA_ROOT / "enriched_index.json"
    if not enriched_path.exists():
        print("enriched_index.json not found, running _enrich_index ...")
        from scripts._enrich_index import main as enrich_main

        enrich_main()

    print(f"Loading enriched index from {DATA_ROOT} ...")
    entries = load_enriched_index()
    print(f"  {len(entries)} entries")

    print("Building KnowledgePointSpec ...")
    root_specs, leaf_specs, subtag_slug_map = build_specs(entries)
    subtag_count = sum(1 for s in leaf_specs if s.is_subtag_node)
    real_leaf_count = len(leaf_specs) - subtag_count
    print(f"  roots: {len(root_specs)}, subtag nodes: {subtag_count}, leaves: {real_leaf_count}")
    merged = sum(1 for s in leaf_specs if len(s.sources) > 1)
    print(f"  merged (multi-source): {merged}")
    total_lectures = sum(len(s.lectures) for s in leaf_specs)
    total_templates = sum(len(s.templates) for s in leaf_specs)
    print(f"  lectures to upsert: {total_lectures}")
    print(f"  templates to upsert: {total_templates}")

    print("\n[1/4] Upserting knowledge points ...")
    slug_to_kp, created_kp = await upsert_knowledge_tree(root_specs, leaf_specs, subtag_slug_map)
    print(f"  created {created_kp} new knowledge points (total {len(slug_to_kp)})")

    # 后续 lectures/templates 只针对真实叶子（subtag 虚拟节点不挂讲义）
    real_leaves = [s for s in leaf_specs if not s.is_subtag_node]
    print("[2/4] Upserting lectures ...")
    created_lec, updated_lec = await upsert_lectures(real_leaves, slug_to_kp)
    print(f"  created {created_lec} new lectures, updated {updated_lec} existing (source migration)")

    print("[3/4] Upserting code templates ...")
    created_tpl = await upsert_code_templates(real_leaves, slug_to_kp)
    print(f"  created {created_tpl} new code templates")

    print("[4/4] Upserting prerequisites ...")
    created_pre = await upsert_prerequisites(slug_to_kp)
    print(f"  created {created_pre} new prerequisite edges")

    print("\n=== Done ===")
    print(f"  knowledge_points: +{created_kp}")
    print(f"  lectures:         +{created_lec} (updated {updated_lec})")
    print(f"  code_templates:   +{created_tpl}")
    print(f"  prerequisites:    +{created_pre}")


if __name__ == "__main__":
    asyncio.run(main())
