"""知识点分类配置（纯数据 + 纯函数，无副作用，无 DB 依赖）。

调整分类只需编辑此文件，然后重新运行：
    python -m scripts._enrich_index   # 重新生成 enriched_index.json
    python -m scripts.seed_knowledge_graph  # 灌库

相关脚本：
- _enrich_index.py：读取 combined_index.json + 本文件 → 生成 enriched_index.json
- _seed_data.py：读取 enriched_index.json → 组装 KnowledgePointSpec（无分类逻辑）
- reorganize_categories.py：DB 层分类归位（从本文件导入 REALLOCATE_MAP）

注：本文件不 import app.models，使用字符串表示枚举值，
    由消费方（_seed_data / reorganize_categories）自行转换。
"""

from __future__ import annotations

# ---- 一级分类 ----

CATEGORY_ROOT_SLUG_PREFIX = "cat-"

CATEGORY_ORDER = [
    "入门",
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
    "CF标签",
]

# ---- 难度映射 ----

OI_CATEGORY_DIFFICULTY: dict[str, str] = {
    "入门": "easy",
    "基础": "easy",
    "语言基础": "easy",
    "简介": "easy",
    "数据结构": "medium",
    "图论": "medium",
    "动态规划": "medium",
    "字符串": "medium",
    "搜索": "medium",
    "数学": "medium",
    "计算几何": "hard",
    "工具": "easy",
    "竞赛": "hard",
    "专题": "hard",
    "杂项": "medium",
    "CF标签": "medium",
}

ZUO_LEVEL_MAP: dict[str, tuple[str, str]] = {
    # (difficulty, lecture_level)
    "入门": ("easy", "card"),
    "必备": ("medium", "standard"),
    "扩展": ("hard", "deep"),
    "进阶": ("hard", "deep"),
}

# ---- 分类覆盖（修复数据源分类错位） ----

SLUG_CATEGORY_OVERRIDE: dict[str, str] = {
    "oi-basic-complexity": "入门",
    "oi-basic-enumerate": "入门",
    "oi-basic-simulate": "入门",
    "oi-basic-divide-and-conquer": "入门",
    "oi-prefix-sum": "入门",
    "oi-sliding-window": "入门",
    "oi-intro-symbol": "数学",
}

# reorganize_categories.py 使用的分类归位映射
# key = 知识点 slug, value = 目标一级分类 slug
REALLOCATE_MAP: dict[str, str] = {
    # —— 入门 ——
    "oi-basic-complexity": "cat-入门",
    "oi-basic-enumerate": "cat-入门",
    "oi-basic-simulate": "cat-入门",
    "oi-basic-divide-and-conquer": "cat-入门",
    "oi-prefix-sum": "cat-入门",
    "oi-sliding-window": "cat-入门",
    # —— 搜索 ——
    "oi-search-alpha-beta": "cat-搜索",
    "oi-search-astar": "cat-搜索",
    "oi-search-backtracking": "cat-搜索",
    "oi-bfs": "cat-搜索",
    "oi-search-bidirectional": "cat-搜索",
    "oi-search-dlx": "cat-搜索",
    "oi-search-heuristic": "cat-搜索",
    "oi-search-idastar": "cat-搜索",
    "oi-search-iterative": "cat-搜索",
    "oi-search-opt": "cat-搜索",
    # —— 竞赛 ——
    "oi-contest-common-mistakes": "cat-竞赛",
    "oi-contest-common-tricks": "cat-竞赛",
    "oi-contest-dictionary": "cat-竞赛",
    "oi-contest-interaction": "cat-竞赛",
    "oi-contest-io": "cat-竞赛",
    "oi-contest-problems": "cat-竞赛",
    # —— 数学 ——
    "oi-intro-symbol": "cat-数学",
}

# ---- 同主题合并（OI-wiki + 左程云去重） ----
# key = 规范化关键词, value = (合并后的 slug 不含 oi- 前缀, 通用中文名, 通用描述)

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
    "最大公约数": ("gcd", "最大公约数", "欧几里得算法求 GCD/LCM"),
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

# ---- CF tag 映射 ----
# 命中映射的 CF tag 合并到对应知识点；未命中的保留为独立节点（归入 CF标签 分类）

CF_TAG_MERGE: dict[str, tuple[str, str]] = {
    "binary search": ("binary-search", "基础"),
    "bitmasks": ("bitmask-dp", "动态规划"),
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

CF_TAG_STANDALONE: set[str] = {
    "*special",
    "communication",
    "expression parsing",
    "implementation",
    "interactive",
    "schedules",
}

# ---- 二级子分类 ----
# { 一级分类: [（子分类名, 关键词列表）] }

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

# ---- 知识点依赖关系 ----
# key = 知识点 slug (不含 oi- 前缀), value = [前置知识点 slug 列表]

PREREQUISITES: dict[str, list[str]] = {
    "sorting": ["array", "binary-search"],
    "binary-search": ["array"],
    "two-pointers": ["array", "sorting"],
    "prefix-sum": ["array"],
    "difference": ["prefix-sum"],
    "greedy": ["sorting"],
    "divide-conquer": ["recursion"],
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
    "dp": ["recursion", "array"],
    "knapsack-dp": ["dp"],
    "tree-dp": ["dp", "tree"],
    "interval-dp": ["dp"],
    "digit-dp": ["dp"],
    "bitmask-dp": ["dp"],
    "slope-dp": ["dp"],
    "kmp": ["string"],
    "manacher": ["string"],
    "ac-automaton": ["kmp", "trie"],
    "string-hash": ["string"],
    "suffix-structure": ["string"],
    "quick-pow": ["recursion"],
    "prime-sieve": ["array"],
    "crt": ["gcd"],
    "linear-basis": ["xor"],
    "gauss-elimination": ["matrix"],
    "fft": ["polynomial"],
    "meet-in-middle": ["brute-force"],
}


# ---- 工具函数 ----


def normalize_title(s: str) -> str:
    """标题小写化用于关键词匹配"""
    return s.lower().replace(" ", "")


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


def clean_zuo_title(raw: str) -> str:
    """清洗左程云标题，去掉编号前缀和"入门题目"等修饰"""
    import re

    s = re.sub(r"^\d+\.\s*", "", raw)
    s = re.sub(r"^[^ -]+?入门题目-", "", s, count=1)
    s = re.sub(r"[-_]\s*[上下]$", "", s)
    return s.strip()
