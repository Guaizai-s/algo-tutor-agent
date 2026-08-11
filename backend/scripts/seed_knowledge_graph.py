"""Seed the knowledge graph from external sources.

Reads ``data/processed/combined_index.json`` plus per-source markdown bodies
and upserts them into ``knowledge_points`` / ``lectures`` / ``code_templates``.

Run from the backend container (``./data`` is mounted at ``/data``):

    docker compose exec backend python -m scripts.seed_knowledge_graph

Idempotent: existing rows are matched by slug and updated in place.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.knowledge import (
    CodeTemplate,
    KnowledgePoint,
    KnowledgePointDifficulty,
    KnowledgePrerequisite,
    Lecture,
    LectureLevel,
)

# data 目录：容器内挂载在 /data，宿主机直接跑时用项目根的 data/
DATA_ROOT = Path("/data/processed")
if not DATA_ROOT.exists():
    DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"

# 14 个一级分类 → 虚拟根 KnowledgePoint 的 slug 前缀
CATEGORY_ROOT_SLUG_PREFIX = "cat-"

# 一级分类顺序（用于 order）
CATEGORY_ORDER = [
    "基础",
    "数据结构",
    "图论",
    "动态规划",
    "字符串",
    "搜索",
    "数学",
    "计算几何",
    "杂项",
    "语言基础",
    "工具",
    "竞赛",
    "简介",
    "专题",
    "CF标签",  # 所有 Codeforces tag 集中归此
]

# 左程云 level -> (KnowledgePointDifficulty, LectureLevel)
ZUO_LEVEL_MAP: dict[str, tuple[KnowledgePointDifficulty, LectureLevel]] = {
    "入门": (KnowledgePointDifficulty.EASY, LectureLevel.CARD),
    "必备": (KnowledgePointDifficulty.MEDIUM, LectureLevel.STANDARD),
    "扩展": (KnowledgePointDifficulty.HARD, LectureLevel.DEEP),
    "进阶": (KnowledgePointDifficulty.HARD, LectureLevel.DEEP),
}

# OI-wiki category -> KnowledgePointDifficulty 推断
OI_CATEGORY_DIFFICULTY: dict[str, KnowledgePointDifficulty] = {
    "基础": KnowledgePointDifficulty.EASY,
    "语言基础": KnowledgePointDifficulty.EASY,
    "简介": KnowledgePointDifficulty.EASY,
    "数据结构": KnowledgePointDifficulty.MEDIUM,
    "图论": KnowledgePointDifficulty.MEDIUM,
    "动态规划": KnowledgePointDifficulty.MEDIUM,
    "字符串": KnowledgePointDifficulty.MEDIUM,
    "搜索": KnowledgePointDifficulty.MEDIUM,
    "数学": KnowledgePointDifficulty.MEDIUM,
    "计算几何": KnowledgePointDifficulty.HARD,
    "工具": KnowledgePointDifficulty.EASY,
    "竞赛": KnowledgePointDifficulty.HARD,
    "专题": KnowledgePointDifficulty.HARD,
    "杂项": KnowledgePointDifficulty.MEDIUM,
}

# 同主题合并的关键词归一化映射：用于 OI-wiki 与左程云去重
# key = 规范化关键词（lowercase），value = (合并后的 KnowledgePoint slug, 通用中文名, 通用描述)
# 当两源的标题都包含同一关键词时，合并到同一个 KnowledgePoint
MERGE_KEYWORDS: dict[str, tuple[str, str, str]] = {
    "线段树": ("seg-tree", "线段树", "区间信息维护数据结构，支持 O(log N) 单点/区间修改与查询"),
    "树状数组": ("fenwick-tree", "树状数组", "基于前缀和的二叉索引结构，常用于单点更新+区间求和"),
    "并查集": ("dsu", "并查集", "维护不相交集合合并与查询的近 O(1) 数据结构"),
    "最短路": ("shortest-path", "最短路", "图上单源/全源最短路径算法（Dijkstra/Bellman-Ford/Floyd 等）"),
    "最小生成树": ("mst", "最小生成树", "连通图最小权值生成树（Kruskal/Prim）"),
    "拓扑排序": ("topo-sort", "拓扑排序", "DAG 节点线性排序，满足所有有向边从前到后"),
    "二分查找": ("binary-search", "二分查找", "在单调/可二分搜索空间中每次排除一半候选"),
    "二分": ("binary-search", "二分查找", "在单调/可二分搜索空间中每次排除一半候选"),
    "排序": ("sorting", "排序", "各类排序算法（冒泡/插入/选择/快排/归并/堆排/基数等）"),
    "贪心": ("greedy", "贪心", "每步取局部最优以期达到全局最优的策略"),
    "动态规划": ("dp", "动态规划", "将问题拆成重叠子问题并保存子问题答案"),
    "背包": ("knapsack-dp", "背包 DP", "01/完全/多重/分组/有依赖背包等动态规划问题"),
    "树型dp": ("tree-dp", "树形 DP", "在树结构上以子树为子问题做动态规划"),
    "树形dp": ("tree-dp", "树形 DP", "在树结构上以子树为子问题做动态规划"),
    "状压": ("bitmask-dp", "状态压缩 DP", "用位掩码压缩集合状态做动态规划"),
    "数位dp": ("digit-dp", "数位 DP", "按数字各位做动态规划，常用于区间计数"),
    "区间dp": ("interval-dp", "区间 DP", "以区间 [l,r] 为状态做动态规划"),
    "kmp": ("kmp", "KMP 算法", "线性时间字符串匹配算法，利用前缀函数避免回溯"),
    "manacher": ("manacher", "Manacher 算法", "线性时间求最长回文子串"),
    "ac自动机": ("ac-automaton", "AC 自动机", "多模式串匹配的 Trie + 失配指针自动机"),
    "字符串哈希": ("string-hash", "字符串哈希", "将子串映射为整数以 O(1) 比较的哈希技术"),
    "前缀树": ("trie", "Trie", "前缀树/字典树，按字符路径存储字符串集合"),
    "trie": ("trie", "Trie", "前缀树/字典树，按字符路径存储字符串集合"),
    "单调栈": ("monotonic-stack", "单调栈", "维护栈内单调性求解下/上一个更大/更小元素"),
    "单调队列": ("monotonic-queue", "单调队列", "维护队列单调性求滑动窗口极值"),
    "滑动窗口": ("sliding-window", "滑动窗口", "维护连续区间在右端扩展左端收缩"),
    "双指针": ("two-pointers", "双指针", "两个位置协同扫描减少重复枚举"),
    "前缀和": ("prefix-sum", "前缀和", "预处理前缀和以 O(1) 求区间和"),
    "差分": ("difference", "差分", "差分数组支持 O(1) 区间加法"),
    "快速幂": ("quick-pow", "快速幂", "O(log n) 计算幂运算，常配合取模"),
    "质数": ("prime", "质数相关", "质数判定、埃氏筛、线性筛等"),
    "质因子": ("prime-factor", "质因数分解", "将整数分解为质数之积"),
    "质数筛": ("prime-sieve", "质数筛", "埃氏筛与线性筛"),
    "最大公约数": ("gcd", "最大公约数", "欧几里得算法求 GGCD/LCM"),
    "欧几里得": ("gcd", "最大公约数", "欧几里得算法求 GCD/LCM"),
    "中国剩余定理": ("crt", "中国剩余定理", "求解同余方程组及其扩展形式"),
    "线性基": ("linear-basis", "线性基", "异或空间下的线性基，求最大异或和等"),
    "高斯消元": ("gauss-elimination", "高斯消元", "线性方程组求解与矩阵消元"),
    "树链剖分": ("hld", "树链剖分", "重链/长链剖分将树路径拆为 O(log n) 段"),
    "lca": ("lca", "最近公共祖先 LCA", "倍增/Tarjan/欧拉序求树上最近公共祖先"),
    "强连通": ("scc", "强连通分量", "Tarjan/Kosaraju 求有向图 SCC 并缩点"),
    "缩点": ("scc", "强连通分量", "Tarjan/Kosaraju 求有向图 SCC 并缩点"),
    "割点": ("cut-vertex", "割点", "无向图割点（关节点）的 Tarjan 算法"),
    "割边": ("bridge", "割边", "无向图桥（割边）的 Tarjan 算法"),
    "双连通": ("biconnected", "双连通分量", "边双/点双连通分量与缩点"),
    "2-sat": ("2-sat", "2-SAT", "布尔可满足性问题的 SCC 解法"),
    "网络流": ("max-flow", "网络流", "最大流/最小割/费用流"),
    "最大流": ("max-flow", "网络流", "最大流/最小割/费用流"),
    "莫队": ("mo-algorithm", "莫队算法", "离线区间查询的分块算法"),
    "分块": ("sqrt-decomposition", "分块", "根号分治思想的数据结构"),
    "cdq": ("cdq-divide", "CDQ 分治", "基于分治处理多维偏序"),
    "整体二分": ("parallel-binary", "整体二分", "对所有查询一起二分答案"),
    "可持久化": ("persistent", "可持久化数据结构", "保留历史版本的数据结构"),
    "树套树": ("seg-in-seg", "树套树", "二维/多层线段树等嵌套结构"),
    "虚树": ("virtual-tree", "虚树", "将关键点压缩为规模更小的树"),
    "点分治": ("centroid-decomposition", "点分治", "以重心为根递归处理树上路径问题"),
    "倍增": ("binary-lifting", "倍增", "预处理 2^k 祖先实现 O(log n) 跳跃"),
    "st表": ("sparse-table", "ST 表", "静态区间极值 O(1) 查询"),
    "莫里斯": ("morris", "Morris 遍历", "O(1) 空间的二叉树遍历"),
    "avl": ("avl-tree", "AVL 树", "严格平衡二叉搜索树"),
    "跳表": ("skiplist", "跳表", "基于随机层的有序链表"),
    "treap": ("treap", "Treap", "树堆，结合 BST 与堆性质"),
    "splay": ("splay-tree", "Splay 树", "自调整二叉搜索树"),
    "左偏树": ("leftist-tree", "左偏树", "可并堆的一种"),
    "红黑树": ("rbtree", "红黑树", "近似平衡的二叉搜索树"),
    # v2 新增：修复跨源/跨分类重复知识点
    "dfs": ("dfs", "DFS 深度优先搜索", "深度优先搜索算法，遍历/搜索树与图数据结构"),
    "深度优先搜索": ("dfs", "DFS 深度优先搜索", "深度优先搜索算法，遍历/搜索树与图数据结构"),
    "bfs": ("bfs", "BFS 广度优先搜索", "广度优先搜索算法，逐层遍历树与图数据结构"),
    "宽度优先": ("bfs", "BFS 广度优先搜索", "广度优先搜索算法，逐层遍历树与图数据结构"),
    "广度优先": ("bfs", "BFS 广度优先搜索", "广度优先搜索算法，逐层遍历树与图数据结构"),
    "树的直径": ("tree-diameter", "树的直径", "树上最远两点距离及其求解方法"),
    "树的重心": ("tree-centroid", "树的重心", "树上使最大子树最小的节点"),
    "卡特兰数": ("catalan", "卡特兰数", "卡特兰数及其在组合计数中的应用"),
    "圆方树": ("block-forest", "圆方树", "处理仙人掌图/点双连通分量的数据结构"),
    "树上启发式合并": ("dsu-on-tree", "树上启发式合并", "DSU on Tree 树上离线统计的启发式合并技术"),
    "分数规划": ("frac-programming", "分数规划/01分数规划", "01分数规划——二分答案+最值判定的优化技术"),
    "博弈论": ("game-theory", "博弈论", "博弈论基础——Nim 游戏、SG 函数等"),
    "替罪羊树": ("sgt", "替罪羊树", "基于部分重建的平衡二叉搜索树"),
    "最近公共祖先": ("lca", "最近公共祖先 LCA", "倍增/Tarjan/欧拉序求树上最近公共祖先"),
    "容斥原理": ("inclusion-exclusion", "容斥原理", "容斥原理在组合计数中的应用"),
    "栈": ("stack", "栈", "后进先出（LIFO）的线性数据结构"),
    "队列": ("queue", "队列", "先进先出（FIFO）的线性数据结构"),
    "链表": ("linked-list", "链表", "链式存储的线性数据结构"),
    "堆": ("heap", "堆", "支持快速获取最值的完全二叉树结构"),
    "递归": ("recursion", "递归", "函数调用自身的编程技巧"),
    "哈希表": ("hash-table", "哈希表", "基于哈希函数实现 O(1) 平均查找的数据结构"),
}


def normalize_title(s: str) -> str:
    """标题小写化用于关键词匹配"""
    return s.lower().replace(" ", "")


# Codeforces tag → 已有知识点 slug 映射
# 命中映射的 CF tag 不再独立成节点，而是把 tag 信息附加到对应知识点
# key = CF tag 英文名（lowercase），value = (知识点 slug 不含前缀, 一级分类)
CF_TAG_MERGE: dict[str, tuple[str, str]] = {
    "binary search": ("binary-search", "基础"),
    "bitmasks": ("bitmask-dp", "动态规划"),  # 位运算主要在状压 DP 出现
    "brute force": ("brute-force", "基础"),
    "chinese remainder theorem": ("crt", "数学"),
    "combinatorics": ("combinatorics", "数学"),
    "constructive algorithms": ("constructive", "基础"),
    "data structures": ("data-structures", "数据结构"),
    "dfs and similar": ("dfs", "图论"),
    "divide and conquer": ("divide-conquer", "基础"),
    "dp": ("dp", "动态规划"),
    "dsu": ("dsu", "数据结构"),
    "fft": ("fft", "数学"),
    "flows": ("max-flow", "图论"),
    "games": ("game-theory", "数学"),
    "geometry": ("geometry", "计算几何"),
    "graph matchings": ("graph-matching", "图论"),
    "graphs": ("graph", "图论"),
    "greedy": ("greedy", "基础"),
    "hashing": ("string-hash", "字符串"),
    "math": ("math", "数学"),
    "matrices": ("matrix", "数学"),
    "meet-in-the-middle": ("meet-in-middle", "搜索"),
    "number theory": ("number-theory", "数学"),
    "probabilities": ("probability", "数学"),
    "shortest paths": ("shortest-path", "图论"),
    "sortings": ("sorting", "基础"),
    "string suffix structures": ("suffix-structure", "字符串"),
    "strings": ("string", "字符串"),
    "ternary search": ("ternary-search", "基础"),
    "trees": ("tree", "数据结构"),
    "two pointers": ("two-pointers", "基础"),
    "2-sat": ("2-sat", "图论"),
}

# 没有对应知识点的 CF tag：保留为独立节点（归到 "CF标签" 分类）
CF_TAG_STANDALONE: set[str] = {
    "*special",
    "communication",
    "expression parsing",
    "implementation",
    "interactive",
    "schedules",
}


# 知识点依赖关系（手工策划，覆盖核心知识点）
# key = 知识点 slug（不含 oi- 前缀），value = [前置知识点 slug 列表]
# 这些关系会写入 knowledge_prerequisites 表，作为图谱的"依赖边"
# 设计依据：OI-wiki 目录结构 + 学习顺序常识
PREREQUISITES: dict[str, list[str]] = {
    # 基础
    "sorting": ["array", "binary-search"],
    "binary-search": ["array"],
    "two-pointers": ["array", "sorting"],
    "prefix-sum": ["array"],
    "difference": ["prefix-sum"],
    "greedy": ["sorting"],
    "divide-conquer": ["recursion"],
    # 数据结构
    "seg-tree": ["fenwick-tree", "recursion"],
    "fenwick-tree": ["prefix-sum"],
    "treap": ["bst"],
    "splay-tree": ["bst"],
    "avl-tree": ["bst"],
    "trie": ["tree"],
    "dsu": ["array"],
    "monotonic-stack": ["stack"],
    "monotonic-queue": ["queue", "monotonic-stack"],
    "hld": ["seg-tree", "lca"],
    "persistent": ["seg-tree"],
    "sparse-table": ["prefix-sum"],
    "mo-algorithm": ["sqrt-decomposition"],
    # 图论
    "shortest-path": ["graph", "dfs"],
    "mst": ["graph", "dsu"],
    "topo-sort": ["graph"],
    "scc": ["graph", "dfs"],
    "lca": ["tree", "binary-lifting"],
    "binary-lifting": ["tree"],
    "max-flow": ["graph", "bfs"],
    "2-sat": ["scc"],
    "cut-vertex": ["graph", "dfs"],
    "bridge": ["graph", "dfs"],
    # 动态规划
    "dp": ["recursion", "array"],
    "knapsack-dp": ["dp"],
    "tree-dp": ["dp", "tree"],
    "interval-dp": ["dp"],
    "digit-dp": ["dp"],
    "bitmask-dp": ["dp"],
    "slope-dp": ["dp"],
    # 字符串
    "kmp": ["string"],
    "manacher": ["string"],
    "ac-automaton": ["kmp", "trie"],
    "string-hash": ["string"],
    "suffix-structure": ["string"],
    # 数学
    "quick-pow": ["recursion"],
    "prime-sieve": ["array"],
    "crt": ["gcd"],
    "linear-basis": ["xor"],
    "gauss-elimination": ["matrix"],
    "fft": ["polynomial"],
    # 搜索
    "meet-in-middle": ["brute-force"],
}


# 二级子分类配置：{ 一级分类: [（子分类名, 关键词列表）] }
# 一个条目的标题若命中某子分类的关键词，则归到该子分类下；
# 若都不命中则归到该一级分类下的 "其他" 子分类（运行时动态生成）
SUBTAGS: dict[str, list[tuple[str, list[str]]]] = {
    "基础": [
        (
            "基础算法",
            ["排序", "二分", "双指针", "贪心", "前缀", "差分", "滑动", "枚举", "暴力", "构造", "递归", "分治", "模拟"],
        ),
        ("搜索", ["搜索", "bfs", "dfs", "astar", "ida", "回溯", "dancing", "启发", "双向", "迭代", "alpha", "meet"]),
    ],
    "动态规划": [
        ("基础 DP", ["基础", "记忆化", "一维", "二维", "三维", "递归"]),
        ("背包 DP", ["背包"]),
        ("树形 DP", ["树型", "树形"]),
        ("区间 DP", ["区间"]),
        ("数位 DP", ["数位"]),
        ("状压 DP", ["状压", "轮廓线", "三进制"]),
        ("DP 优化", ["优化", "斜率", "四边形", "wqs", "slope", "单调队列", "单调栈", "倍增", "预处理"]),
        ("其他 DP", ["计数", "dag", "套dp", "动态dp", "插头", "概率", "博弈", "专题", "决策", "数据量", "观察"]),
    ],
    "数据结构": [
        ("基础数据结构", ["栈", "队列", "链表", "前缀和", "差分", "并查集", "堆", "哈希", "st表", "稀疏表"]),
        (
            "树结构",
            [
                "线段树",
                "树状数组",
                "平衡树",
                "treap",
                "splay",
                "avl",
                "红黑树",
                "sb树",
                "跳表",
                "bst",
                "二叉搜索树",
                "二叉树",
                "trie",
                "前缀树",
                "笛卡尔树",
                "aa树",
                "猫树",
                "霍夫曼",
                "huffman",
                "wblt",
                "手指",
                "finger",
                "左偏",
                "leftist",
                "替罪羊",
                "sgt",
            ],
        ),
        ("可持久化", ["可持久化", "主席树", "持久化"]),
        ("分块与离线", ["分块", "莫队", "离线", "根号", "sqrt", "cdq", "区间最值", "segbeats"]),
        (
            "高级结构",
            [
                "lct",
                "树链剖分",
                "树套树",
                "kd",
                "k-d",
                "虚树",
                "点分治",
                "块状",
                "舞步",
                "舞蹈",
                " dancing",
                "linked-cut",
                "top tree",
                "euler tour",
                "ett",
                "析合",
                "划分",
                "pq",
                "kinetic",
            ],
        ),
        ("字符串结构", ["后缀", "sam", "回文树", "序列自动机"]),
    ],
    "图论": [
        (
            "图基础",
            ["图基础", "存图", "遍历", "dfs", "bfs", "拓扑", "欧拉", "哈密顿", "dag", "有向无环", "连通度", "概念"],
        ),
        ("最短路", ["最短路", "dijkstra", "bellman", "floyd", "johnson", "差分约束", "k短路", "最小环"]),
        ("生成树", ["最小生成树", "生成树", "kruskal", "prim", "次小", "瓶颈"]),
        ("连通性", ["强连通", "缩点", "割点", "割边", "桥", "双连通", "2-sat", "tarjan"]),
        ("网络流", ["网络流", "最大流", "最小割", "费用流", "二分图", "匹配", "匈牙", "dinic", "ek"]),
        (
            "树论",
            [
                "lca",
                "树链",
                "倍增",
                "虚树",
                "点分治",
                "重心",
                "树分治",
                "树基础",
                "树中心",
                "树的直径",
                "树哈希",
                "树上随机",
                "prufer",
                "ahu",
                "树上启发",
                "dsu on tree",
            ],
        ),
        (
            "特殊图论",
            ["圆方", "弦图", "支配树", "斯坦纳", "steiner", "图着色", "最大团", "树形图", "stoer", "平面图", "拆点"],
        ),
        ("图论计数", ["矩阵树", "lgv", "环计数", "随机游走", "图计数"]),
    ],
    "字符串": [
        ("字符串匹配", ["kmp", "ac自动机", "后缀自动机", "z", "exkmp", "bm", "boyer", "lyndon", "最小表示"]),
        ("字符串哈希", ["哈希", "hash"]),
        ("回文与数组", ["manacher", "回文", "后缀数组", "后缀树", "后缀平衡"]),
        ("字符串基础", ["trie", "前缀树", "序列自动机", "标准库"]),
    ],
    "数学": [
        (
            "数论基础",
            ["质数", "素数", "gcd", "lcm", "欧几里得", "扩欧", "逆元", "费马", "欧拉", "中国剩余", "crt", "wilson"],
        ),
        (
            "数论进阶",
            [
                "裴蜀",
                "同余",
                "连分数",
                "离散对数",
                "筛",
                "杜教",
                "类欧",
                "阶乘",
                "升幂",
                "线性同余",
                "卢卡斯",
                "meissel",
                "min25",
                "min_25",
                "模算术",
                "pell",
                "分解",
                "原根",
                "二次域",
                "二次剩余",
                "高次剩余",
                "stern",
                "洲阁",
                "狄利克雷",
                "pollard",
                "powerful",
            ],
        ),
        (
            "组合数学",
            [
                "组合",
                "卡特兰",
                "斯特林",
                "贝尔",
                "排列",
                "容斥",
                "莫比乌斯",
                "反演",
                "二项式",
                "抽屉",
                "伯努利",
                "entringer",
                "eulerian",
                "斐波那契",
                "图论计数",
                "分拆",
                "polya",
                "pólya",
            ],
        ),
        (
            "线性代数",
            [
                "矩阵",
                "高斯",
                "线性基",
                "行列式",
                "对角化",
                "初等变换",
                "jordan",
                "线性映射",
                "内积",
                "外积",
                "向量",
                "线性空间",
            ],
        ),
        ("博弈论", ["博弈", "nim", "sg", "fair"]),
        (
            "多项式",
            [
                "fft",
                "ntt",
                "fwt",
                "多项式",
                "卷积",
                "形式幂级数",
                "chirp",
                "指数生成",
                "egf",
                "ogf",
                "常系数",
                "符号化",
                "代数基本",
            ],
        ),
        ("数值计算", ["快速幂", "快速读", "数值", "牛顿", "积分", "浮点"]),
        ("概率与统计", ["概率", "随机变量", "条件", "不等式", "数字特征"]),
        (
            "代数与数系",
            [
                "群论",
                "环论",
                "域论",
                "布尔",
                "序理论",
                "复数",
                "坐标",
                "进制",
                "格雷码",
                "数字系统",
                "线性规划",
                "单纯形",
                "拟阵",
                "高精度",
                "位操作",
                "二进制集合",
                "插值",
                "schreier",
                "berlekamp",
                "零和",
            ],
        ),
    ],
}


def clean_zuo_title(raw: str) -> str:
    """清洗左程云标题，去掉编号前缀和"入门题目"等修饰，返回规范中文名。

    例：
        "073. 背包dp-01背包、有依赖的背包" → "01背包、有依赖的背包"
        "004. 选择、冒泡、插入排序" → "选择、冒泡、插入排序"
        "010. 链表入门题目-合并两个有序链表" → "合并两个有序链表"
        "005. 对数器-验证的重要手段" → "对数器-验证的重要手段"（保留主题前缀）
    """
    # 去掉 "NNN. " 前缀
    s = re.sub(r"^\d+\.\s*", "", raw)
    # 只去掉明显的修饰前缀（"xxx入门题目-"），保留主题前缀
    s = re.sub(r"^[^ -]+?入门题目-", "", s, count=1)
    # 去掉 "-上" "-下" 后缀（章节标记，不是知识点名）
    s = re.sub(r"[-_]\s*[上下]$", "", s)
    return s.strip()


def find_subtag(category: str, title: str) -> str:
    """返回标题在指定一级分类下应归属的子分类名。未命中返回 '其他'。"""
    subs = SUBTAGS.get(category)
    if not subs:
        return ""
    t = normalize_title(title)
    for sub_name, keywords in subs:
        for kw in keywords:
            if normalize_title(kw) in t:
                return sub_name
    return "其他"


def find_merge(title: str) -> tuple[str, str, str] | None:
    """若标题命中 MERGE_KEYWORDS，返回 (slug, name, description)；否则 None"""
    t = normalize_title(title)
    for kw, spec in MERGE_KEYWORDS.items():
        if normalize_title(kw) in t:
            return spec
    return None


def load_combined_index() -> list[dict]:
    return json.loads((DATA_ROOT / "combined_index.json").read_text(encoding="utf-8"))


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


# ---------------- KnowledgePoint 构建 ----------------


class KnowledgePointSpec:
    """灌库用的知识点规格（合并多源）"""

    def __init__(self, slug: str, name: str, category: str):
        self.slug = slug
        self.name = name
        self.category = category
        self.difficulty: KnowledgePointDifficulty = KnowledgePointDifficulty.MEDIUM
        self.description: str = ""
        self.order: int = 0
        # 二级子分类名（空字符串表示直接挂到一级分类根）
        self.subtag: str = ""
        # 是否为二级子分类虚拟节点
        self.is_subtag_node: bool = False
        # Codeforces 关联
        self.cf_tag: str | None = None
        self.cf_problem_count: int = 0
        # 关联的讲义：(level, title, content) 列表
        self.lectures: list[tuple[LectureLevel, str, str]] = []
        # 关联的模板代码：(language, code, explanation) 列表
        self.templates: list[tuple[str, str, str | None]] = []
        # 来源标记
        self.sources: list[str] = []

    def merge_difficulty(self, d: KnowledgePointDifficulty) -> None:
        """取较难的"""
        rank = {
            KnowledgePointDifficulty.EASY: 1,
            KnowledgePointDifficulty.MEDIUM: 2,
            KnowledgePointDifficulty.HARD: 3,
        }
        if rank[d] > rank[self.difficulty]:
            self.difficulty = d


def build_specs(entries: list[dict]) -> tuple[list[KnowledgePointSpec], list[KnowledgePointSpec]]:
    """从 combined_index 构建 KnowledgePointSpec 列表。

    返回 (root_specs, leaf_specs)。
    root_specs 是 14 个一级分类虚拟根，leaf_specs 是实际知识点。
    """
    # 1) 14 个虚拟根（name 加"分类"后缀避免与叶子同名）
    root_specs: list[KnowledgePointSpec] = []
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

    root_by_cat = {r.category: r for r in root_specs}

    # 2) 叶子节点：按"合并 slug"分组
    # key = 合并 slug 或唯一 slug，value = KnowledgePointSpec
    leaf_map: dict[str, KnowledgePointSpec] = {}
    used_names: set[str] = set()  # name 全局唯一（DB unique 约束）
    # 根节点的 name 已占用，避免叶子与根同名
    for r in root_specs:
        used_names.add(r.name)

    def get_leaf(slug: str, name: str, category: str) -> KnowledgePointSpec:
        if slug not in leaf_map:
            # name 去重：与根/其他叶子冲突时追加 category
            final_name = name
            if final_name in used_names:
                final_name = f"{name}（{category}）"
                # 仍冲突则追加 slug 短哈希
                if final_name in used_names:
                    h = hashlib.md5(slug.encode()).hexdigest()[:6]
                    final_name = f"{name}（{category}-{h}）"
            used_names.add(final_name)
            leaf_map[slug] = KnowledgePointSpec(slug=slug, name=final_name, category=category)
        return leaf_map[slug]

    # 订单计数器（同 category 内按出现顺序）
    cat_counter: dict[str, int] = defaultdict(int)

    # 2a) OI-wiki 条目
    for e in entries:
        if e["source"] != "oi-wiki":
            continue
        category = e["category"]
        merge = find_merge(e["title"])
        if merge:
            slug = f"oi-{merge[0]}"
            leaf = get_leaf(slug, merge[1], category)
            # 合并节点：用通用 name/description（仅首次设置）
            if not leaf.description:
                leaf.description = merge[2]
        else:
            slug = f"oi-{e['slug']}"
            leaf = get_leaf(slug, e["title"], category)
            if not leaf.description:
                leaf.description = f"OI-wiki 知识点：{e['title']}"
        leaf.sources.append("oi-wiki")
        leaf.merge_difficulty(OI_CATEGORY_DIFFICULTY.get(category, KnowledgePointDifficulty.MEDIUM))
        # 设置二级子分类（合并节点用通用名匹配；非合并用原标题匹配）
        sub_name = find_subtag(category, leaf.name) or find_subtag(category, e["title"])
        if leaf.subtag == "" and sub_name:
            leaf.subtag = sub_name
        cat_counter[category] += 1
        leaf.order = root_by_cat[category].order + cat_counter[category]
        # 讲义：DEEP 级
        body = extract_body(read_markdown(e["rel_path"]))
        if body.strip():
            leaf.lectures.append((LectureLevel.DEEP, e["title"], body))

    # 2b) 左程云条目
    for e in entries:
        if e["source"] != "zuo-lecture":
            continue
        category = e["category"]
        level_raw = e["extra"].get("level", "必备")
        level_map = ZUO_LEVEL_MAP.get(level_raw, ZUO_LEVEL_MAP["必备"])
        # 合并：若命中关键词且 OI-wiki 已建过同名合并 slug，则用同一个 slug
        merge = find_merge(e["title"])
        if merge and f"oi-{merge[0]}" in leaf_map:
            slug = f"oi-{merge[0]}"
            leaf = leaf_map[slug]
        elif merge:
            slug = f"oi-{merge[0]}"
            leaf = get_leaf(slug, merge[1], category)
            if not leaf.description:
                leaf.description = merge[2]
        else:
            # 未命中合并关键词，跳过（不创建左程云独立知识点）
            # 左程云内容仅用于为已有 OI-wiki 知识点生成讲义
            continue
        leaf.sources.append("zuo-lecture")
        leaf.merge_difficulty(level_map[0])
        # 设置二级子分类（左程云标题往往带"背包dp-"等前缀，匹配很准）
        sub_name = find_subtag(category, e["title"]) or find_subtag(category, leaf.name)
        if leaf.subtag == "" and sub_name:
            leaf.subtag = sub_name
        cat_counter[category] += 1
        leaf.order = root_by_cat[category].order + cat_counter[category]
        # 讲义：按 level 映射
        body = extract_body(read_markdown(e["rel_path"]))
        if body.strip():
            leaf.lectures.append((level_map[1], clean_zuo_title(e["title"]), body))
        # 模板代码：从左程云 markdown 末尾的代码块提取
        templates = extract_zuo_code_blocks(read_markdown(e["rel_path"]))
        for name, code in templates:
            leaf.templates.append(("java", code, f"模板：{name}"))

    # 2c) Codeforces tag：合并到对应知识点（附加 cf_tag 属性）或保留独立节点
    cf_category = "CF标签"
    # 临时记录 CF 合并信息：(target_slug, cf_tag_en, cf_tag_zh, problem_count)
    cf_merge_info: list[tuple[str, str, str, int]] = []
    for e in entries:
        if e["source"] != "codeforces-tag":
            continue
        tag_en = e["extra"]["tag_en"]
        tag_zh = e["extra"]["tag_zh"]
        problem_count = e["extra"]["problem_count"]
        tag_lower = tag_en.lower()

        if tag_lower in CF_TAG_MERGE:
            # 合并到对应知识点（通过 MERGE_KEYWORDS 已建或将要建的合并 slug）
            base_slug, _category = CF_TAG_MERGE[tag_lower]
            target_slug = f"oi-{base_slug}"
            # 若目标知识点不存在（OI-wiki/左程云都没有），创建一个仅由 CF tag 衍生的节点
            if target_slug not in leaf_map:
                leaf = get_leaf(target_slug, tag_zh, _category)
                if not leaf.description:
                    leaf.description = f"Codeforces 标签 {tag_en}（{tag_zh}）相关知识点"
            else:
                leaf = leaf_map[target_slug]
            leaf.sources.append("codeforces")
            leaf.cf_tag = tag_en
            leaf.cf_problem_count = problem_count
            cf_merge_info.append((target_slug, tag_en, tag_zh, problem_count))
        elif tag_lower in CF_TAG_STANDALONE:
            # 保留为独立节点，归到 CF标签 分类
            slug = e["slug"]  # cf-xxx
            name = f"#{tag_en.replace(' ', '-').replace('*', 'star')}"
            leaf = get_leaf(slug, name, cf_category)
            leaf.sources.append("codeforces")
            leaf.cf_tag = tag_en
            leaf.cf_problem_count = problem_count
            if not leaf.description:
                leaf.description = f"{tag_zh} · {problem_count} 题"
            cat_counter[cf_category] += 1
            leaf.order = root_by_cat[cf_category].order + cat_counter[cf_category]
        else:
            # 未分类的 CF tag，默认保留独立
            slug = e["slug"]
            name = f"#{tag_en.replace(' ', '-')}"
            leaf = get_leaf(slug, name, cf_category)
            leaf.sources.append("codeforces")
            leaf.cf_tag = tag_en
            leaf.cf_problem_count = problem_count
            if not leaf.description:
                leaf.description = f"{tag_zh} · {problem_count} 题"
            cat_counter[cf_category] += 1
            leaf.order = root_by_cat[cf_category].order + cat_counter[cf_category]

    # 3) 为有 subtag 的分类生成二级虚拟节点
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
        spec.difficulty = OI_CATEGORY_DIFFICULTY.get(category, KnowledgePointDifficulty.MEDIUM)
        spec.description = f"{category} → {sub_name}（{cnt} 个知识点）"
        spec.order = root_by_cat[category].order + 500 + len(subtag_specs)
        subtag_specs.append(spec)
        subtag_slug_map[(category, sub_name)] = sub_slug

    # 4) 叶子节点与 subtag 同名时，合并叶子到 subtag（避免"区间 DP（动态规划）"冗余）
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
            target.is_subtag_node = False  # 合并后不再是虚拟节点
            del leaf_map[leaf_slug]

    return root_specs, subtag_specs + list(leaf_map.values()), subtag_slug_map


def extract_zuo_code_blocks(md: str) -> list[tuple[str, str]]:
    """从左程云 markdown 末尾的 `## 模板代码` 段提取 (filename, code) 列表"""
    out: list[tuple[str, str]] = []
    idx = md.find("## 模板代码")
    if idx == -1:
        return out
    section = md[idx:]
    # 匹配 ### `filename` 后的 ```java ... ```
    pat = re.compile(r"### `([^`]+)`\s*\n+```\s*java\n(.*?)\n```", re.S)
    for mm in pat.finditer(section):
        out.append((mm.group(1), mm.group(2)))
    return out


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


async def upsert_lectures(leaf_specs: list[KnowledgePointSpec], slug_to_kp: dict[str, KnowledgePoint]) -> int:
    """幂等写入 Lecture。匹配键：(knowledge_id, title)"""
    created = 0
    async with async_session_maker() as session:
        for spec in leaf_specs:
            kp = slug_to_kp[spec.slug]
            for level, title, content in spec.lectures:
                lec = (
                    await session.execute(
                        select(Lecture).where(
                            Lecture.knowledge_id == kp.id,
                            Lecture.title == title,
                        )
                    )
                ).scalar_one_or_none()
                if lec is None:
                    lec = Lecture(knowledge_id=kp.id, level=level, title=title, content=content)
                    session.add(lec)
                    created += 1
                else:
                    lec.level = level
                    lec.content = content
        await session.commit()
    return created


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


# ---------------- main ----------------


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


async def main() -> None:
    print(f"Loading combined index from {DATA_ROOT} ...")
    entries = load_combined_index()
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
    created_lec = await upsert_lectures(real_leaves, slug_to_kp)
    print(f"  created {created_lec} new lectures")

    print("[3/4] Upserting code templates ...")
    created_tpl = await upsert_code_templates(real_leaves, slug_to_kp)
    print(f"  created {created_tpl} new code templates")

    print("[4/4] Upserting prerequisites ...")
    created_pre = await upsert_prerequisites(slug_to_kp)
    print(f"  created {created_pre} new prerequisite edges")

    print("\n=== Done ===")
    print(f"  knowledge_points: +{created_kp}")
    print(f"  lectures:         +{created_lec}")
    print(f"  code_templates:   +{created_tpl}")
    print(f"  prerequisites:    +{created_pre}")


if __name__ == "__main__":
    asyncio.run(main())
