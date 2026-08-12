"""Insert idempotent diagnostic problems mapped to official knowledge points.

P0-2 验证期创建的 demo-*（验证）知识点已全部清理（见 scripts/migrate_demo_to_official.py），
本脚本仅保留 14 道验证/诊断题，挂载到正式知识点上。幂等，可重复执行。

Run from ``backend`` with a reachable DATABASE_URL:

    python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
from textwrap import dedent

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models.knowledge import KnowledgePoint
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.services.codeforces.sync import sync_cf_tag_knowledge_mappings

PROBLEMS = [
    {
        "slug": "demo-valid-parentheses",
        "title": "有效的括号（验证题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "oi-ds-stack",
        "description": dedent(
            """\
            给定只包含 `()[]{}` 的字符串，判断括号是否有效。
            每个右括号必须与最近一个尚未匹配的同类型左括号配对。

            输出 `true` 或 `false`。
            """
        ),
        "sample_input": "([]){}\n",
        "sample_output": "true\n",
        "hints": ["左括号入栈。", "右括号必须匹配栈顶元素。"],
        "test_cases": [
            {"input": "([]){}\n", "output": "true\n"},
            {"input": "([)]\n", "output": "false\n"},
        ],
    },
    {
        "slug": "demo-binary-search",
        "title": "有序数组二分查找（验证题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "oi-binary-search",
        "description": dedent(
            """\
            给定升序整数数组和目标值 `target`，找到目标值并返回下标；
            如果不存在则返回 `-1`。要求时间复杂度为 O(log n)。
            """
        ),
        "sample_input": "6 9\n-1 0 3 5 9 12\n",
        "sample_output": "4\n",
        "hints": ["维护当前仍可能包含答案的闭区间。", "比较 nums[mid] 和 target。"],
        "test_cases": [
            {"input": "6 9\n-1 0 3 5 9 12\n", "output": "4\n"},
            {"input": "6 2\n-1 0 3 5 9 12\n", "output": "-1\n"},
        ],
    },
    {
        "slug": "demo-longest-substring",
        "title": "无重复字符的最长子串（验证题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "oi-sliding-window",
        "description": "给定字符串 s，返回其中不含重复字符的最长连续子串长度。",
        "sample_input": "abcabcbb\n",
        "sample_output": "3\n",
        "hints": ["维护一个不含重复字符的窗口。", "记录每个字符最近出现的位置。"],
        "test_cases": [
            {"input": "abcabcbb\n", "output": "3\n"},
            {"input": "bbbbb\n", "output": "1\n"},
            {"input": "pwwkew\n", "output": "3\n"},
        ],
    },
    {
        "slug": "demo-coin-change",
        "title": "零钱兑换（验证题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "sub-动态规划-其他",
        "description": dedent(
            """\
            给定若干种硬币面额和总金额 amount，计算凑成该金额所需的最少硬币数。
            如果无法凑成，返回 -1；每种硬币可以使用任意次。
            """
        ),
        "sample_input": "3 11\n1 2 5\n",
        "sample_output": "3\n",
        "hints": ["令 dp[x] 表示凑成金额 x 的最少硬币数。", "从 dp[0] = 0 开始转移。"],
        "test_cases": [
            {"input": "3 11\n1 2 5\n", "output": "3\n"},
            {"input": "1 3\n2\n", "output": "-1\n"},
        ],
    },
    {
        "slug": "demo-number-of-islands",
        "title": "岛屿数量（验证题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "oi-bfs",
        "description": dedent(
            """\
            给定由 `0`（水）和 `1`（陆地）组成的二维网格。
            上下左右相邻的陆地属于同一个岛屿，请返回岛屿数量。
            """
        ),
        "sample_input": "4 5\n11000\n11000\n00100\n00011\n",
        "sample_output": "3\n",
        "hints": ["每块未访问陆地都代表发现了一个新岛屿。", "用 DFS 或 BFS 标记整个岛屿。"],
        "test_cases": [
            {"input": "4 5\n11000\n11000\n00100\n00011\n", "output": "3\n"},
            {"input": "1 5\n11111\n", "output": "1\n"},
        ],
    },
    {
        "slug": "demo-edit-distance",
        "title": "编辑距离（验证题）",
        "difficulty": ProblemDifficulty.HARD,
        "knowledge_slug": "sub-动态规划-其他",
        "description": dedent(
            """\
            给定两个字符串 word1 和 word2，返回将 word1 转换为 word2
            所需的最少操作数。允许插入、删除和替换一个字符。
            """
        ),
        "sample_input": "horse ros\n",
        "sample_output": "3\n",
        "hints": ["状态与两个字符串的前缀长度有关。", "字符相同时无需额外操作。"],
        "test_cases": [
            {"input": "horse ros\n", "output": "3\n"},
            {"input": "intention execution\n", "output": "5\n"},
        ],
    },
    {
        "slug": "demo-trapping-rain-water",
        "title": "接雨水（验证题）",
        "difficulty": ProblemDifficulty.HARD,
        "knowledge_slug": "oi-two-pointers",
        "description": "给定非负整数数组表示柱子高度，计算下雨后能够接住的雨水总量。",
        "sample_input": "12\n0 1 0 2 1 0 1 3 2 1 2 1\n",
        "sample_output": "6\n",
        "hints": ["水量由当前位置左右两侧最高柱的较小值决定。", "可用双指针将空间降至 O(1)。"],
        "test_cases": [
            {"input": "12\n0 1 0 2 1 0 1 3 2 1 2 1\n", "output": "6\n"},
            {"input": "6\n4 2 0 3 2 5\n", "output": "9\n"},
        ],
    },
    {
        "slug": "demo-sort-numbers",
        "title": "整数排序（诊断题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "oi-sorting",
        "description": "给定 n 个整数，按非递减顺序输出。",
        "sample_input": "5\n3 1 4 1 5\n",
        "sample_output": "1 1 3 4 5\n",
        "hints": ["使用语言标准库排序。", "注意相同元素需要全部保留。"],
        "test_cases": [{"input": "5\n3 1 4 1 5\n", "output": "1 1 3 4 5\n"}],
    },
    {
        "slug": "demo-merge-sorted-arrays",
        "title": "合并两个有序数组（诊断题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "oi-two-pointers",
        "description": "合并两个非递减整数数组，并保持输出有序。",
        "sample_input": "3 4\n1 4 7\n2 2 6 8\n",
        "sample_output": "1 2 2 4 6 7 8\n",
        "hints": ["分别维护两个数组的当前位置。"],
        "test_cases": [{"input": "3 4\n1 4 7\n2 2 6 8\n", "output": "1 2 2 4 6 7 8\n"}],
    },
    {
        "slug": "demo-interval-scheduling",
        "title": "最多不重叠区间（诊断题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "oi-greedy",
        "description": "从若干区间中选出最多数量的互不重叠区间。",
        "sample_input": "4\n1 3\n2 4\n3 5\n6 8\n",
        "sample_output": "3\n",
        "hints": ["优先选择结束时间最早的区间。"],
        "test_cases": [{"input": "4\n1 3\n2 4\n3 5\n6 8\n", "output": "3\n"}],
    },
    {
        "slug": "demo-grid-shortest-path",
        "title": "网格最短步数（诊断题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "sub-图论-最短路",
        "description": "在只含可走格与障碍格的网格中，求起点到终点的最少移动步数。",
        "sample_input": "3 3\n...\n.#.\n...\n",
        "sample_output": "4\n",
        "hints": ["所有移动代价相同，使用 BFS。"],
        "test_cases": [{"input": "3 3\n...\n.#.\n...\n", "output": "4\n"}],
    },
    {
        "slug": "demo-topological-order",
        "title": "课程依赖排序（诊断题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "oi-topo-sort",
        "description": "给定有向无环图，输出任意一个合法的拓扑顺序。",
        "sample_input": "4 3\n1 2\n1 3\n3 4\n",
        "sample_output": "1 2 3 4\n",
        "hints": ["维护每个节点的入度。"],
        "test_cases": [{"input": "4 3\n1 2\n1 3\n3 4\n", "output": "1 2 3 4\n"}],
    },
    {
        "slug": "demo-longest-increasing-subsequence",
        "title": "最长递增子序列（诊断题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "sub-动态规划-其他",
        "description": "求整数序列中最长严格递增子序列的长度。",
        "sample_input": "8\n10 9 2 5 3 7 101 18\n",
        "sample_output": "4\n",
        "hints": ["可先考虑 O(n²) 的状态转移。"],
        "test_cases": [{"input": "8\n10 9 2 5 3 7 101 18\n", "output": "4\n"}],
    },
    {
        "slug": "demo-dijkstra",
        "title": "非负权图最短路（诊断题）",
        "difficulty": ProblemDifficulty.HARD,
        "knowledge_slug": "sub-图论-最短路",
        "description": "给定非负边权有向图，求起点到终点的最短距离。",
        "sample_input": "4 5 1 4\n1 2 2\n1 3 5\n2 3 1\n2 4 6\n3 4 1\n",
        "sample_output": "4\n",
        "hints": ["使用优先队列优化 Dijkstra。"],
        "test_cases": [{"input": "4 5 1 4\n1 2 2\n1 3 5\n2 3 1\n2 4 6\n3 4 1\n", "output": "4\n"}],
    },
]

DEFAULT_DIAGNOSTIC_RATING = {
    ProblemDifficulty.EASY: 1000.0,
    ProblemDifficulty.MEDIUM: 1400.0,
    ProblemDifficulty.HARD: 1800.0,
}

# 自建题标签（CF 风格 tag，用于题库筛选与推送匹配）。
# 由标题/知识点语义人工标注，保持与 CF 同步题一致的标签口径。
SLUG_TAGS: dict[str, list[str]] = {
    "demo-valid-parentheses": ["data structures", "stack"],
    "demo-binary-search": ["binary search", "array"],
    "demo-longest-substring": ["two pointers", "sliding window", "hash table"],
    "demo-coin-change": ["dynamic programming"],
    "demo-number-of-islands": ["dfs and similar", "bfs", "graph"],
    "demo-edit-distance": ["dynamic programming", "strings"],
    "demo-trapping-rain-water": ["two pointers", "dynamic programming", "stack"],
    "demo-sort-numbers": ["sorting"],
    "demo-merge-sorted-arrays": ["two pointers", "sorting"],
    "demo-interval-scheduling": ["greedy", "sorting"],
    "demo-grid-shortest-path": ["bfs", "shortest paths"],
    "demo-topological-order": ["graph", "topological sort"],
    "demo-longest-increasing-subsequence": ["dynamic programming", "binary search"],
    "demo-dijkstra": ["shortest paths", "graph"],
}

for _p in PROBLEMS:
    _p.setdefault("cf_tags", SLUG_TAGS.get(_p["slug"], []))


async def seed() -> None:
    async with async_session_maker() as session:
        # 题目挂载的正式知识点 slug → 实体映射
        official_slugs = {item["knowledge_slug"] for item in PROBLEMS}
        kp_rows = (
            (await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug.in_(official_slugs))))
            .scalars()
            .all()
        )
        knowledge_by_slug: dict[str, KnowledgePoint] = {kp.slug: kp for kp in kp_rows}
        created_problems = 0

        for item in PROBLEMS:
            problem = (
                await session.execute(
                    select(Problem).where(Problem.slug == item["slug"]).options(selectinload(Problem.knowledge_points))
                )
            ).scalar_one_or_none()
            if problem is None:
                problem = Problem(slug=item["slug"], title=item["title"], description="")
                session.add(problem)
                created_problems += 1

            problem.title = item["title"]
            problem.description = item["description"].strip()
            problem.difficulty = item["difficulty"]
            problem.cf_rating = item.get("cf_rating", DEFAULT_DIAGNOSTIC_RATING[item["difficulty"]])
            problem.status = ProblemStatus.PUBLISHED
            problem.time_limit_ms = 2000
            problem.memory_limit_kb = 262144
            problem.sample_input = item["sample_input"]
            problem.sample_output = item["sample_output"]
            problem.hints = item["hints"]
            problem.solution_template = {
                "python": "import sys\n\n\ndef solve() -> None:\n    pass\n\n\nif __name__ == '__main__':\n    solve()\n",
                "cpp": "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n",
                "java": "public class Main {\n    public static void main(String[] args) {\n    }\n}\n",
            }
            problem.test_cases = item["test_cases"]
            problem.cf_tags = item.get("cf_tags", [])
            problem.knowledge_points = [knowledge_by_slug[item["knowledge_slug"]]]

        await session.flush()
        mapped_cf = await sync_cf_tag_knowledge_mappings(session)
        await session.commit()

    print(
        "Diagnostic seed complete: " f"{created_problems} problems created, " f"{mapped_cf} CF problem mappings added."
    )


if __name__ == "__main__":
    asyncio.run(seed())
