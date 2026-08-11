"""数据清洗层：从 enriched_index.json 组装 KnowledgePointSpec。

分类逻辑已抽到 _classification_config.py + _enrich_index.py。
本模块仅负责：
1. 读取 enriched_index.json
2. 按 resolved_slug 分组
3. 组装 KnowledgePointSpec（含讲义、模板代码）
4. 构建 root_specs / sub tag 节点

灌库入口：``python -m scripts.seed_knowledge_graph``
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from app.models.knowledge import (
    KnowledgePointDifficulty,
    LectureLevel,
    LectureSource,
)
from scripts._classification_config import (
    CATEGORY_ORDER,
    CATEGORY_ROOT_SLUG_PREFIX,
    OI_CATEGORY_DIFFICULTY,
    ZUO_LEVEL_MAP,
    clean_zuo_title,
)

# ---- 难度/级别字符串 → 枚举转换 ----

_STR_TO_DIFFICULTY: dict[str, KnowledgePointDifficulty] = {
    "easy": KnowledgePointDifficulty.EASY,
    "medium": KnowledgePointDifficulty.MEDIUM,
    "hard": KnowledgePointDifficulty.HARD,
}

_STR_TO_LEVEL: dict[str, LectureLevel] = {
    "card": LectureLevel.CARD,
    "standard": LectureLevel.STANDARD,
    "deep": LectureLevel.DEEP,
}

# data 目录：容器内挂载在 /data，宿主机直接跑时用项目根的 data/
DATA_ROOT = Path("/data/processed")
if not DATA_ROOT.exists():
    DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"


def load_enriched_index() -> list[dict]:
    """读取预计算好的 enriched_index.json"""
    return json.loads((DATA_ROOT / "enriched_index.json").read_text(encoding="utf-8"))


def read_markdown(rel_path: str) -> str:
    """读取 processed markdown 全文（含 frontmatter）"""
    p = DATA_ROOT / rel_path
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def extract_body(md: str) -> str:
    """去掉 frontmatter，返回正文"""
    m = re.match(r"^---\n.*?\n---\n*", md, re.S)
    if m:
        return md[m.end() :]
    return md


def extract_zuo_code_blocks(md: str) -> list[tuple[str, str]]:
    """从左程云 markdown 末尾的 `## 模板代码` 段提取 (filename, code) 列表"""
    out: list[tuple[str, str]] = []
    idx = md.find("## 模板代码")
    if idx == -1:
        return out
    section = md[idx:]
    pat = re.compile(r"### `([^`]+)`\s*\n+```\s*java\n(.*?)\n```", re.S)
    for mm in pat.finditer(section):
        out.append((mm.group(1), mm.group(2)))
    return out


# ---------------- KnowledgePointSpec ----------------


class KnowledgePointSpec:
    """灌库用的知识点规格（合并多源）"""

    def __init__(self, slug: str, name: str, category: str):
        self.slug = slug
        self.name = name
        self.category = category
        self.difficulty: KnowledgePointDifficulty = KnowledgePointDifficulty.MEDIUM
        self.description: str = ""
        self.order: int = 0
        self.subtag: str = ""
        self.is_subtag_node: bool = False
        self.cf_tag: str | None = None
        self.cf_problem_count: int = 0
        self.lectures: list[tuple[LectureLevel, str, str, LectureSource]] = []
        self.templates: list[tuple[str, str, str | None]] = []
        self.sources: list[str] = []

    def merge_difficulty(self, d: KnowledgePointDifficulty) -> None:
        rank = {
            KnowledgePointDifficulty.EASY: 1,
            KnowledgePointDifficulty.MEDIUM: 2,
            KnowledgePointDifficulty.HARD: 3,
        }
        if rank[d] > rank[self.difficulty]:
            self.difficulty = d


def _parse_difficulty(val: str) -> KnowledgePointDifficulty:
    """将 enriched JSON 中的难度字符串转为枚举"""
    try:
        return KnowledgePointDifficulty(val)
    except ValueError:
        return KnowledgePointDifficulty.MEDIUM


# ---------------- build_specs ----------------


def build_specs(
    entries: list[dict],
) -> tuple[list[KnowledgePointSpec], list[KnowledgePointSpec], dict[tuple[str, str], str]]:
    """从 enriched_index.json 条目构建 KnowledgePointSpec 列表。

    分类决策已在 enrichment 阶段完成，此函数仅负责：
    1. 创建一级分类根节点
    2. 按 resolved_slug 分组 → 组装 KnowledgePointSpec
    3. 生成二级子分类虚拟节点
    4. 叶子与 subtag 同名时合并

    返回 (root_specs, leaf_specs, subtag_slug_map)。
    """
    # ---- 1) 一级分类根节点 ----
    root_specs: list[KnowledgePointSpec] = []
    root_by_cat: dict[str, KnowledgePointSpec] = {}
    for i, cat in enumerate(CATEGORY_ORDER):
        root = KnowledgePointSpec(
            slug=f"{CATEGORY_ROOT_SLUG_PREFIX}{cat}",
            name=f"{cat}分类",
            category=cat,
        )
        root.difficulty = KnowledgePointDifficulty.EASY
        root.description = f"{cat}分类根节点"
        root.order = i * 1000
        root_specs.append(root)
        root_by_cat[cat] = root

    # ---- 2) 按 resolved_slug 分组条目 ----
    slug_groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        slug_groups[e["resolved_slug"]].append(e)

    leaf_map: dict[str, KnowledgePointSpec] = {}
    used_names: set[str] = {r.name for r in root_specs}

    def get_leaf(slug: str, name: str, category: str) -> KnowledgePointSpec:
        if slug not in leaf_map:
            final_name = name
            if final_name in used_names:
                final_name = f"{name}（{category}）"
                if final_name in used_names:
                    h = hashlib.md5(slug.encode()).hexdigest()[:6]
                    final_name = f"{name}（{category}-{h}）"
            used_names.add(final_name)
            leaf_map[slug] = KnowledgePointSpec(slug=slug, name=final_name, category=category)
        return leaf_map[slug]

    for slug, group in slug_groups.items():
        primary = group[0]
        category = primary["resolved_category"]
        name = primary["resolved_name"]
        subtag = primary.get("resolved_subtag", "")
        description = primary.get("resolved_description", "")
        order = primary.get("resolved_order", 0)
        difficulty = _parse_difficulty(primary.get("resolved_difficulty", "medium"))

        leaf = get_leaf(slug, name, category)
        leaf.description = description or leaf.description
        leaf.merge_difficulty(difficulty)
        if subtag and not leaf.subtag:
            leaf.subtag = subtag
        if order:
            leaf.order = order

        # 收集 CF 元数据
        for e in group:
            if e.get("cf_tag"):
                leaf.cf_tag = e["cf_tag"]
                leaf.cf_problem_count = e.get("cf_problem_count", 0)

        # 收集来源标记
        for e in group:
            src = e["source"]
            if src not in leaf.sources:
                leaf.sources.append(src)

        # 组装讲义 & 模板
        for e in group:
            src = e["source"]
            rel_path = e.get("rel_path", "")

            if src == "oi-wiki":
                body = extract_body(read_markdown(rel_path))
                if body.strip():
                    leaf.lectures.append((LectureLevel.DEEP, e["title"], body, LectureSource.OI_WIKI))

            elif src == "zuo-lecture":
                level_raw = e["extra"].get("level", "必备") if "extra" in e else "必备"
                diff_str, level_str = ZUO_LEVEL_MAP.get(level_raw, ZUO_LEVEL_MAP["必备"])
                md_text = read_markdown(rel_path)
                body = extract_body(md_text)
                if body.strip():
                    leaf.lectures.append(
                        (_STR_TO_LEVEL[level_str], clean_zuo_title(e["title"]), body, LectureSource.ZUO_LECTURE)
                    )
                # 模板代码
                templates = extract_zuo_code_blocks(md_text)
                for tpl_name, code in templates:
                    leaf.templates.append(("java", code, f"模板：{tpl_name}"))

    # ---- 3) 二级子分类虚拟节点 ----
    subtag_counter: dict[tuple[str, str], int] = defaultdict(int)
    for leaf in leaf_map.values():
        if leaf.subtag:
            subtag_counter[(leaf.category, leaf.subtag)] += 1

    subtag_specs: list[KnowledgePointSpec] = []
    subtag_slug_map: dict[tuple[str, str], str] = {}
    subtag_used_names: set[str] = set()
    for (category, sub_name), cnt in subtag_counter.items():
        sub_slug = f"sub-{category}-{sub_name}".replace(" ", "-")
        final_name = sub_name
        if final_name in used_names or final_name in subtag_used_names:
            final_name = f"{sub_name}（{category}）"
            if final_name in subtag_used_names:
                h = hashlib.md5(sub_slug.encode()).hexdigest()[:6]
                final_name = f"{sub_name}（{category}-{h}）"
        subtag_used_names.add(final_name)
        spec = KnowledgePointSpec(slug=sub_slug, name=final_name, category=category)
        spec.is_subtag_node = True
        diff_str = OI_CATEGORY_DIFFICULTY.get(category, "medium")
        spec.difficulty = _STR_TO_DIFFICULTY.get(diff_str, KnowledgePointDifficulty.MEDIUM)
        spec.description = f"{category} → {sub_name}（{cnt} 个知识点）"
        spec.order = root_by_cat[category].order + 500 + len(subtag_specs)
        subtag_specs.append(spec)
        subtag_slug_map[(category, sub_name)] = sub_slug

    # ---- 4) 叶子与 subtag 同名时合并 ----
    subtag_by_name: dict[str, KnowledgePointSpec] = {}
    for ss in subtag_specs:
        subtag_by_name[ss.name] = ss
    for leaf_slug, leaf in list(leaf_map.items()):
        if leaf.name in subtag_by_name:
            target = subtag_by_name[leaf.name]
            target.lectures.extend(leaf.lectures)
            target.templates.extend(leaf.templates)
            target.sources.extend(leaf.sources)
            if leaf.description and not target.description:
                target.description = leaf.description
            if leaf.cf_tag and not target.cf_tag:
                target.cf_tag = leaf.cf_tag
                target.cf_problem_count = leaf.cf_problem_count
            target.merge_difficulty(leaf.difficulty)
            target.is_subtag_node = False
            del leaf_map[leaf_slug]

    return root_specs, subtag_specs + list(leaf_map.values()), subtag_slug_map
