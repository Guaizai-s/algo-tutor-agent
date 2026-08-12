"""从数据源补灌缺失的基础算法知识点（幂等，只处理 TARGET_SLUGS）。

背景：enriched_index.json 已定义 oi-sorting / oi-binary-search / oi-greedy /
oi-two-pointers（合并 OI-wiki + 左程云讲义 + CF 标签），但数据库缺少这些节点，
导致 CF 题只能挂到临时的 demo-*（验证）知识点上。本脚本把这些正式节点补灌进库，
挂到已存在的 sub-基础-基础算法 下，设置 cf_tag 供 CF 标签映射复用。

与 seed_knowledge_graph 的区别：只 upsert 目标 slug，不重排/覆盖其它知识点，
避免打乱已手动组织好的图谱。

用法（backend 容器内，data 挂载于 /data）：
    docker compose exec backend python -m scripts.seed_missing_basics
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import CodeTemplate, KnowledgePoint, Lecture
from scripts._seed_data import build_specs, load_enriched_index

# 目标：与 demo-*（验证）知识点对应的正式知识点
TARGET_SLUGS = {"oi-sorting", "oi-binary-search", "oi-greedy", "oi-two-pointers"}

# 父节点：数据库已存在的「基础 → 基础算法」subtag 虚拟节点
PARENT_SLUG = "sub-基础-基础算法"


async def main() -> None:
    entries = load_enriched_index()
    _roots, leaf_specs, _subtag_map = build_specs(entries)
    targets = [s for s in leaf_specs if s.slug in TARGET_SLUGS and not s.is_subtag_node]

    missing = TARGET_SLUGS - {s.slug for s in targets}
    if missing:
        print(f"WARN: 数据源中缺少目标知识点: {missing}")

    async with async_session_maker() as session:
        parent = (
            await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == PARENT_SLUG))
        ).scalar_one_or_none()
        if parent is None:
            print(f"FATAL: 父节点不存在: {PARENT_SLUG}")
            return

        created_kp = 0
        slug_to_kp: dict[str, KnowledgePoint] = {}
        for spec in targets:
            kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == spec.slug))
            ).scalar_one_or_none()
            if kp is None:
                kp = KnowledgePoint(slug=spec.slug, name=spec.name)
                session.add(kp)
                created_kp += 1
            kp.name = spec.name
            kp.description = spec.description
            kp.difficulty = spec.difficulty
            kp.order = spec.order
            kp.parent_id = parent.id
            kp.cf_tag = spec.cf_tag
            kp.cf_problem_count = spec.cf_problem_count
            slug_to_kp[spec.slug] = kp
        await session.flush()

        created_lec = 0
        for spec in targets:
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
                    session.add(Lecture(knowledge_id=kp.id, level=level, title=title, content=content, source=source))
                    created_lec += 1
                else:
                    lec.level = level
                    lec.content = content
                    lec.source = source

        created_tpl = 0
        for spec in targets:
            kp = slug_to_kp[spec.slug]
            existing = (
                (await session.execute(select(CodeTemplate).where(CodeTemplate.knowledge_id == kp.id))).scalars().all()
            )
            keys = {(t.language, t.template_code[:200]) for t in existing}
            for lang, code, explanation in spec.templates:
                if (lang, code[:200]) in keys:
                    continue
                session.add(
                    CodeTemplate(knowledge_id=kp.id, language=lang, template_code=code, explanation=explanation)
                )
                keys.add((lang, code[:200]))
                created_tpl += 1

        await session.commit()

    print(f"补灌完成: knowledge_points +{created_kp}, lectures +{created_lec}, templates +{created_tpl}")
    for s in targets:
        print(
            f"  {s.slug} | {s.name} | cf_tag={s.cf_tag} | " f"lectures={len(s.lectures)} | templates={len(s.templates)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
