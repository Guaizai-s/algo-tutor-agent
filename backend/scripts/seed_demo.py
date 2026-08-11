"""Insert idempotent demo knowledge points, lectures, and problems.

Run from ``backend`` with a reachable DATABASE_URL:

    python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
from textwrap import dedent

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models.knowledge import (
    KnowledgePoint,
    KnowledgePointDifficulty,
    KnowledgePrerequisite,
    Lecture,
    LectureLevel,
)
from app.models.problem import Problem, ProblemDifficulty, ProblemStatus
from app.services.codeforces.sync import sync_cf_tag_knowledge_mappings

KNOWLEDGE = [
    {
        "slug": "demo-array-hash",
        "name": "数组与哈希表（验证）",
        "description": "使用数组保存顺序数据，使用哈希表以额外空间换取接近 O(1) 的查询。",
        "difficulty": KnowledgePointDifficulty.EASY,
        "order": 10,
        "lecture": "数组适合按下标访问；哈希表适合快速判断元素是否出现。两数之和是典型的一次遍历哈希题。",
    },
    {
        "slug": "demo-stack",
        "name": "栈（验证）",
        "description": "后进先出（LIFO）数据结构，常用于括号匹配、表达式求值和单调栈。",
        "difficulty": KnowledgePointDifficulty.EASY,
        "order": 20,
        "lecture": "遇到左括号入栈，遇到右括号检查并弹出匹配的左括号；结束时栈必须为空。",
    },
    {
        "slug": "demo-binary-search",
        "name": "二分查找（验证）",
        "description": "在有序或具有单调性的搜索空间中，每次排除一半候选答案。",
        "difficulty": KnowledgePointDifficulty.EASY,
        "order": 30,
        "lecture": "维护闭区间 [left, right] 时，循环条件使用 left <= right；根据中点值缩小区间。",
    },
    {
        "slug": "demo-sliding-window",
        "name": "滑动窗口（验证）",
        "description": "维护一个连续区间，在右端扩展并在不满足条件时移动左端。",
        "difficulty": KnowledgePointDifficulty.MEDIUM,
        "order": 40,
        "lecture": "滑动窗口常将枚举所有子数组的 O(n²) 优化为 O(n)。关键是维护窗口内状态和左指针。",
    },
    {
        "slug": "demo-dynamic-programming",
        "name": "动态规划（验证）",
        "description": "将问题拆成重叠子问题，并保存子问题答案以避免重复计算。",
        "difficulty": KnowledgePointDifficulty.MEDIUM,
        "order": 50,
        "lecture": "动态规划需要明确状态、转移、初始值和遍历顺序。零钱兑换可定义 dp[x] 为凑成金额 x 的最少硬币数。",
    },
    {
        "slug": "demo-graph-search",
        "name": "图搜索（验证）",
        "description": "使用 DFS 或 BFS 遍历图、网格及其连通分量。",
        "difficulty": KnowledgePointDifficulty.MEDIUM,
        "order": 60,
        "lecture": "网格可以视为隐式图。发现一块未访问陆地后执行 DFS/BFS，并把整个连通分量标记为已访问。",
    },
    {
        "slug": "demo-two-pointers",
        "name": "双指针（验证）",
        "description": "使用两个位置协同扫描，减少重复枚举。",
        "difficulty": KnowledgePointDifficulty.HARD,
        "order": 70,
        "lecture": "接雨水可用左右指针和左右最高柱。较低一侧的最高值决定该侧当前位置能接的水量。",
    },
    {
        "slug": "demo-sorting",
        "name": "排序（验证）",
        "description": "按指定键重排数据，是二分、贪心和双指针等算法的常见前置步骤。",
        "difficulty": KnowledgePointDifficulty.EASY,
        "order": 25,
        "lecture": "排序后，相邻关系与单调性会显现。需要同时考虑排序键、稳定性和整体时间复杂度。",
    },
    {
        "slug": "demo-greedy",
        "name": "贪心（验证）",
        "description": "在每一步选择当前最优决策，并证明局部最优能够导向全局最优。",
        "difficulty": KnowledgePointDifficulty.MEDIUM,
        "order": 45,
        "lecture": "贪心算法的关键不是选择本身，而是交换论证或单调性证明。区间调度通常按结束时间排序。",
    },
    {
        "slug": "demo-shortest-paths",
        "name": "最短路（验证）",
        "description": "在带权或无权图中寻找从起点到其他节点的最小代价路径。",
        "difficulty": KnowledgePointDifficulty.HARD,
        "order": 65,
        "lecture": "无权图使用 BFS；非负边权图使用 Dijkstra。松弛操作用于持续改进当前最短距离。",
    },
]

CF_TAG_BY_KNOWLEDGE_SLUG = {
    "demo-array-hash": "data structures",
    "demo-stack": "data structures",
    "demo-binary-search": "binary search",
    "demo-sliding-window": "two pointers",
    "demo-dynamic-programming": "dp",
    "demo-graph-search": "dfs and similar",
    "demo-two-pointers": "two pointers",
    "demo-sorting": "sortings",
    "demo-greedy": "greedy",
    "demo-shortest-paths": "shortest paths",
}

PREREQUISITES = [
    ("demo-sorting", "demo-array-hash"),
    ("demo-binary-search", "demo-sorting"),
    ("demo-greedy", "demo-sorting"),
    ("demo-sliding-window", "demo-two-pointers"),
    ("demo-shortest-paths", "demo-graph-search"),
]


PROBLEMS = [
    {
        "slug": "demo-two-sum",
        "title": "两数之和（验证题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "demo-array-hash",
        "description": dedent(
            """\
            给定一个整数数组 `nums` 和整数 `target`，请返回和为 `target`
            的两个元素下标。保证恰好存在一个答案，且同一元素不能重复使用。

            输入：第一行是数组长度和 target，第二行是数组元素。
            输出：两个下标，按从小到大输出。
            """
        ),
        "sample_input": "4 9\n2 7 11 15\n",
        "sample_output": "0 1\n",
        "hints": ["遍历时记录已经见过的数字。", "查找 target - nums[i] 是否已经在哈希表中。"],
        "test_cases": [
            {"input": "4 9\n2 7 11 15\n", "output": "0 1\n"},
            {"input": "3 6\n3 2 3\n", "output": "0 2\n"},
        ],
    },
    {
        "slug": "demo-valid-parentheses",
        "title": "有效的括号（验证题）",
        "difficulty": ProblemDifficulty.EASY,
        "knowledge_slug": "demo-stack",
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
        "knowledge_slug": "demo-binary-search",
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
        "knowledge_slug": "demo-sliding-window",
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
        "knowledge_slug": "demo-dynamic-programming",
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
        "knowledge_slug": "demo-graph-search",
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
        "knowledge_slug": "demo-dynamic-programming",
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
        "knowledge_slug": "demo-two-pointers",
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
        "knowledge_slug": "demo-sorting",
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
        "knowledge_slug": "demo-two-pointers",
        "description": "合并两个非递减整数数组，并保持输出有序。",
        "sample_input": "3 4\n1 4 7\n2 2 6 8\n",
        "sample_output": "1 2 2 4 6 7 8\n",
        "hints": ["分别维护两个数组的当前位置。"],
        "test_cases": [
            {"input": "3 4\n1 4 7\n2 2 6 8\n", "output": "1 2 2 4 6 7 8\n"}
        ],
    },
    {
        "slug": "demo-interval-scheduling",
        "title": "最多不重叠区间（诊断题）",
        "difficulty": ProblemDifficulty.MEDIUM,
        "knowledge_slug": "demo-greedy",
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
        "knowledge_slug": "demo-shortest-paths",
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
        "knowledge_slug": "demo-graph-search",
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
        "knowledge_slug": "demo-dynamic-programming",
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
        "knowledge_slug": "demo-shortest-paths",
        "description": "给定非负边权有向图，求起点到终点的最短距离。",
        "sample_input": "4 5 1 4\n1 2 2\n1 3 5\n2 3 1\n2 4 6\n3 4 1\n",
        "sample_output": "4\n",
        "hints": ["使用优先队列优化 Dijkstra。"],
        "test_cases": [
            {"input": "4 5 1 4\n1 2 2\n1 3 5\n2 3 1\n2 4 6\n3 4 1\n", "output": "4\n"}
        ],
    },
]

DEFAULT_DIAGNOSTIC_RATING = {
    ProblemDifficulty.EASY: 1000.0,
    ProblemDifficulty.MEDIUM: 1400.0,
    ProblemDifficulty.HARD: 1800.0,
}


async def seed() -> None:
    async with async_session_maker() as session:
        knowledge_by_slug: dict[str, KnowledgePoint] = {}
        created_knowledge = 0
        created_lectures = 0
        created_problems = 0

        for item in KNOWLEDGE:
            kp = (
                await session.execute(select(KnowledgePoint).where(KnowledgePoint.slug == item["slug"]))
            ).scalar_one_or_none()
            if kp is None:
                kp = KnowledgePoint(slug=item["slug"], name=item["name"])
                session.add(kp)
                created_knowledge += 1
            kp.name = item["name"]
            kp.description = item["description"]
            kp.difficulty = item["difficulty"]
            kp.order = item["order"]
            kp.cf_tag = CF_TAG_BY_KNOWLEDGE_SLUG[item["slug"]]
            knowledge_by_slug[item["slug"]] = kp

        await session.flush()

        for knowledge_slug, prerequisite_slug in PREREQUISITES:
            knowledge_id = knowledge_by_slug[knowledge_slug].id
            prerequisite_id = knowledge_by_slug[prerequisite_slug].id
            existing = (
                await session.execute(
                    select(KnowledgePrerequisite).where(
                        KnowledgePrerequisite.knowledge_id == knowledge_id,
                        KnowledgePrerequisite.prerequisite_id == prerequisite_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    KnowledgePrerequisite(
                        knowledge_id=knowledge_id,
                        prerequisite_id=prerequisite_id,
                    )
                )

        for item in KNOWLEDGE:
            kp = knowledge_by_slug[item["slug"]]
            title = f"{item['name']}知识卡片"
            lecture = (
                await session.execute(
                    select(Lecture).where(
                        Lecture.knowledge_id == kp.id,
                        Lecture.title == title,
                    )
                )
            ).scalar_one_or_none()
            if lecture is None:
                lecture = Lecture(
                    knowledge_id=kp.id,
                    level=LectureLevel.CARD,
                    title=title,
                    content=item["lecture"],
                )
                session.add(lecture)
                created_lectures += 1
            else:
                lecture.level = LectureLevel.CARD
                lecture.content = item["lecture"]

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
            problem.cf_rating = item.get(
                "cf_rating", DEFAULT_DIAGNOSTIC_RATING[item["difficulty"]]
            )
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
            problem.knowledge_points = [knowledge_by_slug[item["knowledge_slug"]]]

        await session.flush()
        mapped_cf = await sync_cf_tag_knowledge_mappings(session)
        await session.commit()

    print(
        "Demo seed complete: "
        f"{created_knowledge} knowledge points, "
        f"{created_lectures} lectures, "
        f"{created_problems} problems created, "
        f"{mapped_cf} CF problem mappings added."
    )


if __name__ == "__main__":
    asyncio.run(seed())
