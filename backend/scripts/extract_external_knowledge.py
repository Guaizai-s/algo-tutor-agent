"""Extract knowledge content from external sources into structured Markdown.

Sources (cloned under ``data/external/``):
- OI-wiki        : docs/**/*.md                 -> data/processed/oi-wiki/<cat>/<slug>.md
- 左程云讲义      : ppt/*.pptx|*.pdf + src/class*  -> data/processed/zuo-lecture/<id>_<title>.md

Output ``data/processed/index.json`` aggregates a manifest for later DB seeding.

Run from project root:

    python -m backend.scripts.extract_external_knowledge

Requires (host-side, NOT in backend/requirements.txt):
- python-pptx, pdfplumber  (already installed on this machine)
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber
from pptx import Presentation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXT_ROOT = PROJECT_ROOT / "data" / "external"
OUT_ROOT = PROJECT_ROOT / "data" / "processed"

# OI-wiki 顶层目录 -> 中文分类映射（保守映射，未命中的归 misc）
OI_CATEGORY_MAP = {
    "basic": "基础",
    "dp": "动态规划",
    "ds": "数据结构",
    "graph": "图论",
    "geometry": "计算几何",
    "lang": "语言基础",
    "math": "数学",
    "search": "搜索",
    "string": "字符串",
    "topic": "专题",
    "misc": "杂项",
    "tools": "工具",
    "contest": "竞赛",
    "intro": "简介",
}

# 左程云讲义编号 -> 主题分类（按 ppt 文件名【xxx】里的标签 + 标题关键词粗分）
ZUO_LEVEL_MAP = {
    "入门": "入门",
    "必备": "必备",
    "扩展": "扩展",
    "挺难": "进阶",
}

# 左程云讲义标题 -> 主题分类（与 OI-wiki/CF 一级分类对齐）
# 顺序敏感：先匹配的关键词优先
ZUO_TOPIC_KEYWORDS: list[tuple[str, str]] = [
    # 图论
    ("并查集", "图论"),
    ("拓扑排序", "图论"),
    ("最小生成树", "图论"),
    ("广搜", "图论"),
    ("双向广搜", "图论"),
    ("建图", "图论"),
    ("强连通", "图论"),
    ("缩点", "图论"),
    ("割点", "图论"),
    ("割边", "图论"),
    ("双连通", "图论"),
    ("圆方树", "图论"),
    ("2-SAT", "图论"),
    ("差分约束", "图论"),
    ("同余最短路", "图论"),
    ("负环", "图论"),
    ("欧拉路径", "图论"),
    ("欧拉", "图论"),
    ("基环树", "图论"),
    ("仙人掌", "图论"),
    ("树链剖分", "图论"),
    ("树上差分", "图论"),
    ("树的重心", "图论"),
    ("树的直径", "图论"),
    ("换根dp", "图论"),
    ("树分治", "图论"),
    ("点分治", "图论"),
    ("点分树", "图论"),
    ("边分治", "图论"),
    ("虚树", "图论"),
    ("dsu on tree", "图论"),
    ("启发式合并", "图论"),
    ("LCA", "图论"),
    ("floyd", "图论"),
    ("bellman", "图论"),
    ("spfa", "图论"),
    ("dijkstra", "图论"),
    ("最短路", "图论"),
    ("网络流", "图论"),
    ("最大流", "图论"),
    # 数据结构
    ("线段树", "数据结构"),
    ("树状数组", "数据结构"),
    ("树套树", "数据结构"),
    ("主席树", "数据结构"),
    ("可持久化", "数据结构"),
    ("块状", "数据结构"),
    ("分块", "数据结构"),
    ("莫队", "数据结构"),
    ("CDQ", "数据结构"),
    ("整体二分", "数据结构"),
    ("单调栈", "数据结构"),
    ("单调队列", "数据结构"),
    ("前缀树", "数据结构"),
    ("trie", "数据结构"),
    ("AC自动机", "数据结构"),
    ("KMP", "字符串"),
    ("Manacher", "字符串"),
    ("字符串哈希", "字符串"),
    ("哈希", "数据结构"),
    ("二叉树", "数据结构"),
    ("链表", "数据结构"),
    ("队列", "数据结构"),
    ("栈", "数据结构"),
    ("堆", "数据结构"),
    ("AVL", "数据结构"),
    ("跳表", "数据结构"),
    ("替罪羊树", "数据结构"),
    ("Treap", "数据结构"),
    ("Splay", "数据结构"),
    ("左偏树", "数据结构"),
    ("有序表", "数据结构"),
    ("位图", "数据结构"),
    ("LRU", "数据结构"),
    # 动态规划
    ("动态规划", "动态规划"),
    ("dp", "动态规划"),
    ("背包", "动态规划"),
    ("树型dp", "动态规划"),
    ("树形dp", "动态规划"),
    ("状压", "动态规划"),
    ("数位dp", "动态规划"),
    ("区间dp", "动态规划"),
    ("轮廓线", "动态规划"),
    ("博弈", "动态规划"),  # 左程云把博弈放 dp
    # 数学
    ("质数", "数学"),
    ("质因子", "数学"),
    ("质数筛", "数学"),
    ("快速幂", "数学"),
    ("矩阵快速幂", "数学"),
    ("逆元", "数学"),
    ("同余", "数学"),
    ("容斥", "数学"),
    ("最大公约数", "数学"),
    ("裴蜀", "数学"),
    ("欧几里得", "数学"),
    ("中国剩余定理", "数学"),
    ("线性基", "数学"),
    ("高斯消元", "数学"),
    ("二项式", "数学"),
    ("康托", "数学"),
    ("约瑟夫", "数学"),
    ("卡特兰", "数学"),
    ("数论", "数学"),
    # 字符串（覆盖 KMP 那条之外）
    ("字符串", "字符串"),
    ("后缀", "字符串"),
    # 基础
    ("排序", "基础"),
    ("二分", "基础"),
    ("前缀和", "基础"),
    ("差分", "基础"),
    ("滑动窗口", "基础"),
    ("双指针", "基础"),
    ("异或", "基础"),
    ("位运算", "基础"),
    ("贪心", "基础"),
    ("递归", "基础"),
    ("对数器", "基础"),
    ("复杂度", "基础"),
    ("输入和输出", "基础"),
    ("二进制", "基础"),
    ("归并分治", "基础"),
    ("随机选择", "基础"),
    ("数据结构设计", "基础"),
    ("数据量猜解法", "基础"),
    ("前缀信息", "基础"),
    ("子数组", "基础"),
    ("递增子序列", "基础"),
    ("01分数规划", "基础"),
    # 搜索
    ("洪水填充", "搜索"),
    ("宽度优先", "搜索"),
    ("Morris", "搜索"),
    # 数据结构（补充）
    ("ST表", "数据结构"),
    ("倍增", "数据结构"),
    ("Kruskal重构", "数据结构"),
    ("LCT", "数据结构"),
    # 计算几何
    # 语言基础 / 语言
    # 简介类
    ("社会实验", "简介"),
    ("语言问题", "简介"),
    ("入门提醒", "简介"),
    ("算法和数据结构简介", "简介"),
]


def classify_zuo_topic(title: str) -> str:
    """按标题关键词匹配主题分类"""
    t = title.lower()
    for kw, cat in ZUO_TOPIC_KEYWORDS:
        if kw.lower() in t:
            return cat
    return "杂项"


@dataclass
class DocEntry:
    source: str  # "oi-wiki" | "zuo-lecture"
    category: str
    slug: str
    title: str
    rel_path: str  # 相对 OUT_ROOT 的 markdown 路径
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip()).strip("-")
    return s or "untitled"


# ---------------- OI-wiki ----------------


def iter_oi_md() -> Iterable[Path]:
    docs = EXT_ROOT / "OI-wiki" / "docs"
    for p in docs.rglob("*.md"):
        # 跳过 _static、images、index 等
        if "_static" in p.parts or "images" in p.parts:
            continue
        if p.name in ("index.md", "edit-landing.md"):
            continue
        yield p


def extract_oi_title(content: str, fallback: str) -> str:
    # OI-wiki md 顶部一般是 `# 标题`
    m = re.match(r"^#\s+(.+)$", content, re.M)
    return m.group(1).strip() if m else fallback


def load_oi_nav_titles() -> dict[str, str]:
    """解析 OI-wiki mkdocs.yml 的 nav，返回 {相对路径: 中文标题}。

    mkdocs.yml 的 nav 行格式：``      - 中文标题: path/to.md``
    """
    mkdocs = EXT_ROOT / "OI-wiki" / "mkdocs.yml"
    if not mkdocs.exists():
        return {}
    titles: dict[str, str] = {}
    # 仅匹配 `- 标题: 路径.md` 行（路径以 .md 结尾）
    pat = re.compile(r"^\s*-\s+(.+?):\s+(\S+\.md)\s*$")
    for line in mkdocs.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if not m:
            continue
        title, path = m.group(1).strip(), m.group(2).strip()
        # 跳过纯分类节点（如 "简介:" 不带 .md）
        titles[path] = title
    return titles


def process_oi_wiki() -> list[DocEntry]:
    entries: list[DocEntry] = []
    skipped_empty = 0
    nav_titles = load_oi_nav_titles()
    for md in iter_oi_md():
        rel = md.relative_to(EXT_ROOT / "OI-wiki" / "docs")
        rel_posix = rel.as_posix()
        category_en = rel.parts[0] if rel.parts else "misc"
        category = OI_CATEGORY_MAP.get(category_en, "杂项")
        content = md.read_text(encoding="utf-8", errors="ignore")
        # 跳过上游占位空文档（OI-wiki 有少量 .md 是 0 字节或仅 author 行）
        if len(content.strip()) < 50:
            skipped_empty += 1
            continue
        # 标题优先级：mkdocs.yml nav > md 内 # 标题 > 文件名
        title = nav_titles.get(rel_posix) or extract_oi_title(content, md.stem)

        slug = slugify(rel.with_suffix("").as_posix().replace("/", "-"))
        out_md = OUT_ROOT / "oi-wiki" / category / f"{slug}.md"
        out_md.parent.mkdir(parents=True, exist_ok=True)
        # 在头部加 frontmatter，便于后续灌库
        front = (
            f"---\n"
            f"source: oi-wiki\n"
            f"category: {category}\n"
            f"category_en: {category_en}\n"
            f"path: {rel.as_posix()}\n"
            f"title: {title}\n"
            f"---\n\n"
        )
        out_md.write_text(front + content, encoding="utf-8")
        entries.append(
            DocEntry(
                source="oi-wiki",
                category=category,
                slug=slug,
                title=title,
                rel_path=str(out_md.relative_to(OUT_ROOT)),
                extra={"category_en": category_en, "origin_path": rel.as_posix()},
            )
        )
    return entries


# ---------------- 左程云讲义 ----------------

ZUO_PPT_DIR = EXT_ROOT / "algorithm-journey" / "ppt"
ZUO_SRC_DIR = EXT_ROOT / "algorithm-journey" / "src"


def parse_zuo_filename(fname: str) -> tuple[int, str, str] | None:
    """算法讲解073【必备】背包dp-01背包、有依赖的背包.pptx -> (73, '必备', '背包dp-01背包、有依赖的背包')"""
    stem = Path(fname).stem
    m = re.match(r"^算法讲解(\d+)【([^】]+)】\s*(.+)$", stem)
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3).strip()


def extract_pptx_text(path: Path) -> list[tuple[int, str, list[str]]]:
    """返回 [(page, title, [paragraphs...])]"""
    prs = Presentation(path)
    pages = []
    for i, slide in enumerate(prs.slides, start=1):
        title = ""
        body: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                txt = "".join(run.text for run in para.runs).strip()
                if not txt:
                    continue
                # 第一个占位符视为标题
                if not title and shape.shape_type == 14:  # PLACEHOLDER
                    title = txt
                else:
                    body.append(txt)
            if not title and body:
                title = body.pop(0)
        pages.append((i, title or f"第{i}页", body))
    return pages


def extract_pdf_text(path: Path) -> list[tuple[int, str, list[str]]]:
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            title = lines[0] if lines else f"第{i}页"
            body = lines[1:] if lines else []
            pages.append((i, title, body))
    return pages


def collect_zuo_code(class_num: int) -> list[dict]:
    """收集 src/classNNN/ 下所有 java 文件"""
    d = ZUO_SRC_DIR / f"class{class_num:03d}"
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.java")):
        out.append(
            {
                "name": f.name,
                "path": str(f.relative_to(EXT_ROOT)),
                "content": f.read_text(encoding="utf-8", errors="ignore"),
            }
        )
    return out


def process_zuo_lectures() -> list[DocEntry]:
    entries: list[DocEntry] = []
    files = sorted(ZUO_PPT_DIR.iterdir(), key=lambda p: p.name)
    for f in files:
        if f.suffix.lower() not in (".pptx", ".pdf"):
            continue
        parsed = parse_zuo_filename(f.name)
        if not parsed:
            continue
        num, level_raw, title = parsed
        level = ZUO_LEVEL_MAP.get(level_raw, level_raw)
        topic = classify_zuo_topic(title)

        if f.suffix.lower() == ".pptx":
            pages = extract_pptx_text(f)
        else:
            pages = extract_pdf_text(f)

        codes = collect_zuo_code(num)

        slug = slugify(f"{num:03d}-{title}")
        out_md = OUT_ROOT / "zuo-lecture" / f"{slug}.md"
        out_md.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = [
            "---",
            "source: zuo-lecture",
            f"lecture_no: {num}",
            f"level: {level}",
            f"level_raw: {level_raw}",
            f"topic: {topic}",
            f"title: {title}",
            f"origin_file: {f.name}",
            f"code_files: {len(codes)}",
            "---",
            "",
            f"# {num:03d}. {title}",
            "",
            f"> 难度标签：**{level}** ｜ 主题：**{topic}** ｜ 来源：左程云《算法讲解》第 {num} 讲",
            "",
        ]
        for page_no, ptitle, body in pages:
            lines.append(f"## 第 {page_no} 页：{ptitle}")
            lines.append("")
            if body:
                lines.extend(body)
                lines.append("")
            else:
                lines.append("（本页无正文文本，可能为示意图）")
                lines.append("")

        if codes:
            lines.append("## 模板代码")
            lines.append("")
            for c in codes:
                lines.append(f"### `{c['name']}`")
                lines.append("")
                lines.append("```java")
                lines.append(c["content"])
                lines.append("```")
                lines.append("")
        out_md.write_text("\n".join(lines), encoding="utf-8")

        entries.append(
            DocEntry(
                source="zuo-lecture",
                category=topic,
                slug=slug,
                title=f"{num:03d}. {title}",
                rel_path=str(out_md.relative_to(OUT_ROOT)),
                tags=[topic, level],
                extra={
                    "lecture_no": num,
                    "level": level,
                    "topic": topic,
                    "origin_file": f.name,
                    "code_files": len(codes),
                    "pages": len(pages),
                },
            )
        )
    return entries


# ---------------- main ----------------


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    all_entries: list[DocEntry] = []

    print("[1/3] Extracting OI-wiki ...")
    all_entries.extend(process_oi_wiki())
    print(f"  -> {sum(1 for e in all_entries if e.source == 'oi-wiki')} docs")

    print("[2/3] Extracting 左程云讲义 (pptx+pdf) ...")
    all_entries.extend(process_zuo_lectures())
    print(f"  -> {sum(1 for e in all_entries if e.source == 'zuo-lecture')} lectures")

    print("[3/3] Writing index.json ...")
    (OUT_ROOT / "index.json").write_text(
        json.dumps([asdict(e) for e in all_entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    by_source: dict[str, int] = {}
    for e in all_entries:
        by_source[e.source] = by_source.get(e.source, 0) + 1
    print("\n=== Summary ===")
    for k, v in by_source.items():
        print(f"  {k}: {v}")
    print(f"  total: {len(all_entries)}")
    print(f"\nOutput: {OUT_ROOT}")


if __name__ == "__main__":
    main()
