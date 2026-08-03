"""Fetch Codeforces problemset tags and problems via official API.

Output to ``data/processed/codeforces/``:
- tags.json         : 38 个 tag 的频次统计 + 中英映射
- problems.jsonl    : 全量题目（contestId/index/name/tags/rating），逐行 JSON
- tag_problems.json : 按 tag 聚合的题目清单（每个 tag 最多 200 道按 rating 排序）

API doc: https://codeforces.com/apiHelp/methods#problemset.problems
Rate limit: 1 req/sec（本脚本只调 1 次）

Run from project root:

    python -m backend.scripts.fetch_codeforces
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = PROJECT_ROOT / "data" / "processed" / "codeforces"

API_URL = "https://codeforces.com/api/problemset.problems"

# CF 英文 tag -> (中文显示名, 一级分类) 一级分类与 OI-wiki 对齐
# 一级分类 ∈：基础/数据结构/图论/动态规划/字符串/数学/搜索/计算几何/杂项
TAG_MAP: dict[str, tuple[str, str]] = {
    # 基础
    "implementation": ("实现模拟", "基础"),
    "brute force": ("暴力枚举", "基础"),
    "greedy": ("贪心", "基础"),
    "constructive algorithms": ("构造算法", "基础"),
    "sortings": ("排序", "基础"),
    "two pointers": ("双指针", "基础"),
    "binary search": ("二分查找", "基础"),
    "bitmasks": ("位运算", "基础"),
    "meet-in-the-middle": ("折半搜索", "基础"),
    "ternary search": ("三分查找", "基础"),
    # 数据结构
    "data structures": ("数据结构", "数据结构"),
    "dsu": ("并查集", "数据结构"),
    "hashing": ("哈希", "数据结构"),
    # 图论
    "graphs": ("图论", "图论"),
    "dfs and similar": ("DFS", "图论"),
    "trees": ("树", "图论"),
    "shortest paths": ("最短路", "图论"),
    "flows": ("网络流", "图论"),
    "graph matchings": ("图匹配", "图论"),
    "2-sat": ("2-SAT", "图论"),
    # 动态规划
    "dp": ("动态规划", "动态规划"),
    "divide and conquer": ("分治", "动态规划"),
    # 字符串
    "strings": ("字符串", "字符串"),
    "string suffix structures": ("后缀结构", "字符串"),
    "expression parsing": ("表达式解析", "字符串"),
    # 数学
    "math": ("数学", "数学"),
    "number theory": ("数论", "数学"),
    "combinatorics": ("组合数学", "数学"),
    "matrices": ("矩阵", "数学"),
    "fft": ("FFT", "数学"),
    "probabilities": ("概率", "数学"),
    "games": ("博弈论", "数学"),
    "chinese remainder theorem": ("中国剩余定理", "数学"),
    # 搜索
    # 计算几何
    "geometry": ("计算几何", "计算几何"),
    # 杂项 / 竞赛
    "interactive": ("交互题", "杂项"),
    "schedules": ("调度", "杂项"),
    "communication": ("通信", "杂项"),
    "*special": ("特殊题", "杂项"),
}


def fetch() -> dict:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "algo-tutor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    print("Fetching codeforces problemset.problems ...")
    t0 = time.time()
    data = fetch()
    if data.get("status") != "OK":
        raise RuntimeError(f"CF API failed: {data}")
    problems = data["result"]["problems"]
    print(f"  got {len(problems)} problems in {time.time() - t0:.1f}s")

    # 1) tags.json
    from collections import Counter

    tag_counter: Counter[str] = Counter()
    for p in problems:
        for t in p.get("tags", []):
            tag_counter[t] += 1
    tags_meta = []
    unmapped = []
    for tag, n in tag_counter.most_common():
        mapped = TAG_MAP.get(tag)
        if mapped:
            zh, cat = mapped
        else:
            zh, cat = tag, "杂项"
            unmapped.append(tag)
        tags_meta.append({"tag_en": tag, "tag_zh": zh, "category": cat, "problem_count": n})
    (OUT_ROOT / "tags.json").write_text(json.dumps(tags_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  tags.json: {len(tags_meta)} tags ({len(unmapped)} unmapped: {unmapped})")

    # 2) problems.jsonl
    with (OUT_ROOT / "problems.jsonl").open("w", encoding="utf-8") as f:
        for p in problems:
            f.write(
                json.dumps(
                    {
                        "contestId": p.get("contestId"),
                        "index": p.get("index"),
                        "name": p.get("name"),
                        "rating": p.get("rating"),
                        "tags": p.get("tags", []),
                        "url": f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"  problems.jsonl: {len(problems)} problems")

    # 3) tag_problems.json: 每个 tag 下按 rating 排序的题目（最多保留 200 道）
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in problems:
        for t in p.get("tags", []):
            by_tag[t].append(p)
    tag_problems = {}
    for tag, plist in by_tag.items():
        plist_sorted = sorted(
            plist,
            key=lambda x: (x.get("rating") is None, x.get("rating") or 0, x["name"]),
        )
        tag_problems[tag] = [
            {
                "contestId": p["contestId"],
                "index": p["index"],
                "name": p["name"],
                "rating": p.get("rating"),
                "url": f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
            }
            for p in plist_sorted[:200]
        ]
    (OUT_ROOT / "tag_problems.json").write_text(
        json.dumps(tag_problems, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  tag_problems.json: {len(tag_problems)} tags (each capped at 200)")

    print(f"\nOutput: {OUT_ROOT}")


if __name__ == "__main__":
    main()
