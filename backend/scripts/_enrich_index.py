"""预计算知识点分类，生成 enriched_index.json。

读取 combined_index.json，应用 _classification_config 中的分类规则，
为每个条目预计算分类决策（slug、category、subtag 等），写入 enriched_index.json。

运行：
    cd backend && python -m scripts._enrich_index

usage:
    在 seed_knowledge_graph 之前运行（或作为其前置步骤自动调用）。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from scripts._classification_config import (
    CATEGORY_ORDER,
    CF_TAG_MERGE,
    CF_TAG_STANDALONE,
    OI_CATEGORY_DIFFICULTY,
    SLUG_CATEGORY_OVERRIDE,
    ZUO_LEVEL_MAP,
    find_merge,
    find_subtag,
)

# data 目录：容器内挂载在 /data，宿主机直接跑时用项目根的 data/
DATA_ROOT = Path("/data/processed")
if not DATA_ROOT.exists():
    DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"


def load_combined_index() -> list[dict]:
    return json.loads((DATA_ROOT / "combined_index.json").read_text(encoding="utf-8"))


def enrich(entries: list[dict]) -> list[dict]:
    """为每个条目添加 resolved_* 字段，预计算分类决策。

    返回 enriched entries（保留原始字段 + 新增 resolved 字段）。
    """
    # 一级分类 order 映射
    cat_order = {cat: i * 1000 for i, cat in enumerate(CATEGORY_ORDER)}
    cat_counter: dict[str, int] = defaultdict(int)

    enriched: list[dict] = []

    # ---- Phase 1: OI-wiki entries ----
    oi_slug_set: set[str] = set()

    for e in entries:
        if e["source"] != "oi-wiki":
            continue

        category = SLUG_CATEGORY_OVERRIDE.get(f"oi-{e['slug']}", e["category"])
        merge = find_merge(e["title"])

        if merge:
            resolved_slug = f"oi-{merge[0]}"
            resolved_name = merge[1]
            resolved_description = merge[2]
        else:
            resolved_slug = f"oi-{e['slug']}"
            resolved_name = e["title"]
            resolved_description = f"OI-wiki 知识点：{e['title']}"

        difficulty = OI_CATEGORY_DIFFICULTY.get(category, "medium")
        subtag = find_subtag(category, resolved_name) or find_subtag(category, e["title"])

        cat_counter[category] += 1
        order = cat_order.get(category, 0) + cat_counter[category]

        oi_slug_set.add(resolved_slug)

        enriched.append(
            {
                **e,
                "resolved_slug": resolved_slug,
                "resolved_name": resolved_name,
                "resolved_category": category,
                "resolved_subtag": subtag,
                "resolved_difficulty": difficulty,
                "resolved_description": resolved_description,
                "resolved_order": order,
            }
        )

    # ---- Phase 2: zuo-lecture entries ----
    for e in entries:
        if e["source"] != "zuo-lecture":
            continue

        merge = find_merge(e["title"])
        if merge and f"oi-{merge[0]}" in oi_slug_set:
            resolved_slug = f"oi-{merge[0]}"
            resolved_name = merge[1]
            category = e["category"]
            difficulty = ZUO_LEVEL_MAP.get(e["extra"].get("level", "必备"), ZUO_LEVEL_MAP["必备"])[0]
            subtag = find_subtag(category, e["title"]) or ""
            description = merge[2]
        elif merge:
            resolved_slug = f"oi-{merge[0]}"
            resolved_name = merge[1]
            category = e["category"]
            difficulty = ZUO_LEVEL_MAP.get(e["extra"].get("level", "必备"), ZUO_LEVEL_MAP["必备"])[0]
            subtag = find_subtag(category, e["title"]) or ""
            description = merge[2]
            oi_slug_set.add(resolved_slug)
        else:
            # 未命中合并关键词，跳过（左程云仅用于补充 OI-wiki 知识点）
            continue

        cat_counter[category] += 1
        order = cat_order.get(category, 0) + cat_counter[category]

        enriched.append(
            {
                **e,
                "resolved_slug": resolved_slug,
                "resolved_name": resolved_name,
                "resolved_category": category,
                "resolved_subtag": subtag,
                "resolved_difficulty": difficulty,
                "resolved_description": description,
                "resolved_order": order,
            }
        )

    # ---- Phase 3: Codeforces tag entries ----
    cf_category = "CF标签"

    for e in entries:
        if e["source"] != "codeforces-tag":
            continue

        tag_en = e["extra"]["tag_en"]
        tag_zh = e["extra"]["tag_zh"]
        problem_count = e["extra"]["problem_count"]
        tag_lower = tag_en.lower()

        if tag_lower in CF_TAG_MERGE:
            base_slug, _category = CF_TAG_MERGE[tag_lower]
            resolved_slug = f"oi-{base_slug}"
            resolved_name = tag_zh
            category = _category
            difficulty = OI_CATEGORY_DIFFICULTY.get(category, "medium")
            if resolved_slug not in oi_slug_set:
                # 创建仅由 CF tag 衍生的节点
                resolved_description = f"Codeforces 标签 {tag_en}（{tag_zh}）相关知识点"
                oi_slug_set.add(resolved_slug)
            else:
                resolved_description = ""
            resolved_subtag = ""

        elif tag_lower in CF_TAG_STANDALONE:
            resolved_slug = e["slug"]
            resolved_name = f"#{tag_en.replace(' ', '-').replace('*', 'star')}"
            category = cf_category
            difficulty = OI_CATEGORY_DIFFICULTY.get(cf_category, "medium")
            resolved_description = f"{tag_zh} · {problem_count} 题"
            resolved_subtag = ""

        else:
            # 未分类 CF tag → 独立节点
            resolved_slug = e["slug"]
            resolved_name = f"#{tag_en.replace(' ', '-')}"
            category = cf_category
            difficulty = OI_CATEGORY_DIFFICULTY.get(cf_category, "medium")
            resolved_description = f"{tag_zh} · {problem_count} 题"
            resolved_subtag = ""

        cat_counter[category] += 1
        order = cat_order.get(category, 0) + cat_counter[category]

        enriched.append(
            {
                **e,
                "resolved_slug": resolved_slug,
                "resolved_name": resolved_name,
                "resolved_category": category,
                "resolved_subtag": resolved_subtag,
                "resolved_difficulty": difficulty,
                "resolved_description": resolved_description,
                "resolved_order": order,
                "cf_tag": tag_en,
                "cf_problem_count": problem_count,
            }
        )

    return enriched


def main() -> None:
    print("Loading combined_index.json ...")
    entries = load_combined_index()
    print(f"  {len(entries)} raw entries")

    enriched = enrich(entries)
    print(f"  {len(enriched)} enriched entries")

    # 按 resolved_slug 去重统计
    slugs = set(e["resolved_slug"] for e in enriched)
    print(f"  {len(slugs)} unique knowledge point slugs")

    output_path = DATA_ROOT / "enriched_index.json"
    output_path.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
