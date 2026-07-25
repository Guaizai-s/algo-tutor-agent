# 算法教练平台 Spec

## 项目定位

**本平台是面向 ACM/ICPC 算法竞赛的 AI 教练系统，首要服务对象是 ACM 弱校学生。**

### 核心使命
- **给 ACM 弱校一个参赛机会**：弱校缺乏教练、缺乏学长传帮带、缺乏系统训练规划，AI 教练补位这三块短板
- **目标赛事**：ICPC 区域赛（Asia Regional）与省赛，目标奖牌梯度：铜牌 → 银牌 → 金牌
- **不做面试向**：知识点体系、题库、训练路径全部对齐 ACM 大纲，不为求职面试做剪裁
- **不做通识向**：不覆盖 CLRS 式大学课程内容，聚焦竞赛所需

### 用户画像
- 起点：C++ 语法基础（或愿意 1-2 周补齐），无竞赛经验
- 终点：能在 ICPC 区域赛 stable 拿铜，部分学生冲击银牌
- 痛点：自学 OI-wiki 没有路径感、刷题没有复盘、Virtual Participation 找不到队友

## Why
构建一个 AI 驱动的算法学习平台，从"被动刷题"升级为"AI 教练主动教学"，支持个性化学习路径与组队训练。

## What Changes
- 新建完整的算法教练平台，包含前端、后端、AI 服务
- 实现用户系统、知识库、题库、CF 同步、复习、组队等核心模块
- **BREAKING**: 无（全新项目）

## Impact
- Affected specs: 无（全新项目）
- Affected code: 全新代码库

---

## 合规与法律约束

本平台严格遵守以下合规边界，所有功能设计不得突破：

### 题面版权
- **不存储** Codeforces / 洛谷 / AtCoder 等第三方 OJ 的题面正文
- 题库表只存元数据（外链 ID、名称、tags、rating）+ 跳转链接
- 自建种子题库的题面必须为原创或 CC-BY 授权来源（如 USACO）

### 提交代码版权
- 用户提交的代码版权属于用户本人
- 平台**不主动抓取**用户在 CF 上的源代码（CF API 也不提供）
- 用户在平台内提交的代码由用户自主上传，平台获得展示授权

### 第三方资料
- **oi-wiki**（CC-BY-SA 4.0）：可作为 RAG 语料，衍生作品需同协议开源
- **左程云 PPT**：只引用事实性元数据（class 编号、标题、难度标签、前置声明），**不入 RAG 库，不入 Lecture 表**
- **Codeforces API**：合规调用，遵守 1 次/2 秒速率限制，需服务端缓存

### LLM 服务
- 不调用 OpenAI API（国内合规问题）
- 使用国内合规 LLM 服务（DeepSeek / 通义 / 智谱）
- 限制每用户每日调用次数（默认 20 次/天）

---

## ADDED Requirements

### Requirement: 用户认证与档案
系统 SHALL 支持用户注册、登录、个人资料管理，并包含 ACM 场景必需的归属字段。

#### Scenario: 用户注册登录
- **WHEN** 用户使用邮箱+密码注册
- **THEN** 系统创建账户，返回 JWT Token

#### Scenario: ACM 档案字段
- **WHEN** 用户完善个人资料
- **THEN** 系统记录：学校（必填）、CF handle（可选）、AtCoder handle（可选）、目标奖牌梯度（铜/银/金）

#### Scenario: CF 账号绑定
- **WHEN** 用户填写 CF handle
- **THEN** 系统调用 CF API `user.info` 验证 handle 存在，并拉取当前 Rating 作为初始数据

---

### Requirement: 知识点体系与讲义
系统 SHALL 维护算法知识点图谱（含前置依赖关系），每个知识点支持三级粒度教学材料。

#### Scenario: 知识点骨架来源
- **WHEN** 初始化知识点树
- **THEN** 系统以 oi-wiki 的 mkdocs.yml nav 树为骨架，按 ACM 剪枝标准裁剪：
  - 保留：basic / search / dp / string / ds / graph / math 基础
  - 删除：math/poly（多项式）、math/number-theory 高级数论、math/algebra 抽象代数
  - 目标节点数 ~200

#### Scenario: 知识点浏览
- **WHEN** 用户查看知识点树
- **THEN** 系统展示知识点图谱，标注已学/未学/薄弱状态，以及前置依赖关系

#### Scenario: 讲义三级粒度
- **WHEN** 用户进入某个知识点
- **THEN** 系统展示三级粒度材料：
  - CARD：知识卡片（5 分钟阅读，概念+适用场景+复杂度）
  - STANDARD：标准讲义（含模板代码 + 例题）
  - DEEP：题型专题（如"区间 DP 经典 8 题"，合并多个相关知识点）

#### Scenario: 讲义内容来源
- **WHEN** 生成讲义正文
- **THEN** 系统由 AI 基于 oi-wiki 对应章节重写，不直接复制左程云 PPT 或任何版权材料

---

### Requirement: RAG 知识库
系统 SHALL 基于 RAG 架构存储和检索算法知识，支持讲义内容检索和 AI 问答。

#### Scenario: 知识检索问答
- **WHEN** 用户提问（如"DP 怎么推状态转移方程？"）
- **THEN** 系统从知识库检索相关讲义片段，结合国内 LLM 生成个性化回答，并附上引用来源

#### Scenario: 讲义内容入库
- **WHEN** 管理员上传新讲义
- **THEN** 系统自动切片、向量化并存入 pgvector 知识库

#### Scenario: RAG 语料范围
- **WHEN** 构建 RAG 知识库
- **THEN** 系统只使用合规语料：
  - oi-wiki markdown（CC-BY-SA 4.0）
  - 平台自建讲义（自有版权）
  - **不包含**左程云 PPT 全文、CF 题面、洛谷题面

#### Scenario: LLM 调用限制
- **WHEN** 用户触发 LLM 问答
- **THEN** 系统检查用户当日调用次数，超过 20 次/天则拒绝并提示次日再来

---

### Requirement: 题库管理
系统 SHALL 维护算法题库，按四层来源结构组织，不存储任何第三方题面正文。

#### Scenario: Tier 1 - CF 外链题目
- **WHEN** 同步 CF 题库
- **THEN** 系统调用 CF API `problemset.problems` 拉取元数据（contestId, index, name, tags, rating），存入 Problem 表，**不存题面**
- **AND** 用户点击题目时跳转到 CF 原页面

#### Scenario: Tier 2 - 自建种子题库
- **WHEN** 管理员录入自建题目
- **THEN** 系统存储完整题面（原创或 CC-BY 来源），并触发 AI 标注知识点
- **AND** 自建题目标记 `source="platform"`，可被平台内判题/题解功能使用

#### Scenario: Tier 4 - 用户自报题目
- **WHEN** 用户粘贴外部题目到平台
- **THEN** 系统存储用户提供的题面（用户对内容负责），并触发 AI 标注知识点

#### Scenario: 题目-知识点映射
- **WHEN** 建立题目与知识点的关联
- **THEN** 系统维护 `ProblemKnowledgePoint` 表，含置信度与来源：
  - `source="cf_tag"`：CF 原始 tag 映射，confidence=0.6
  - `source="ai_analysis"`：AI 分析题面（仅自建/用户自报题目），confidence=0.8
  - `source="user_feedback"`：用户做题后主动反馈，confidence=0.9
  - `source="consensus"`：10+ 用户共识标注，confidence=1.0

#### Scenario: 题目浏览与筛选
- **WHEN** 用户按知识点和难度筛选题目
- **THEN** 系统返回匹配的题目列表，含 CF rating 与平台掌握度统计

---

### Requirement: Codeforces 数据同步
系统 SHALL 通过 CF API 同步用户提交记录与题目元数据，所有数据需服务端缓存以遵守速率限制。

#### Scenario: 用户提交记录增量同步
- **WHEN** Celery 定时任务触发（每用户每 5 分钟一次）
- **THEN** 系统调用 CF API `user.status`（从上次同步点增量拉取），写入 Submission 表
- **AND** Submission 表只存元数据（verdict / time / memory / passed_test_count），**不存源代码**

#### Scenario: 题目元数据同步
- **WHEN** Celery 每日任务触发
- **THEN** 系统调用 CF API `problemset.problems` 全量刷新 Problem 表的元数据

#### Scenario: 速率限制保护
- **WHEN** 调用 CF API
- **THEN** 系统保证请求间隔 ≥ 2 秒，失败时指数退避重试

#### Scenario: CF Rating 同步
- **WHEN** 用户绑定 CF handle 或每日定时任务触发
- **THEN** 系统调用 `user.rating` 拉取 Rating 历史，存入用户档案并展示 Rating 曲线

---

### Requirement: 水平测试与冷启动
系统 SHALL 在用户首次进入时完成水平诊断，生成知识点掌握度初始快照。

#### Scenario: 绑定 CF 的冷启动
- **WHEN** 用户已绑定 CF handle 且 CF 上有 ≥ 20 条提交记录
- **THEN** 系统拉取 `user.status`，按题目 cf_tags 映射到知识点，聚合计算各知识点 mastery
- **AND** 按 CF Rating 定训练目标（<1200 铜牌向 / 1200-1600 银牌向 / 1600-2000 金牌向 / >2000 高级向）

#### Scenario: 未绑 CF 的冷启动
- **WHEN** 用户未绑定 CF 或 CF 提交 < 20 条
- **THEN** 系统从自建种子题库（Tier 2）选 15 道诊断题（覆盖 10 个核心知识点，5 易+7 中+3 难）
- **AND** 用户在平台内做题，系统根据 AC 情况推断掌握度

#### Scenario: 起点定标
- **WHEN** 掌握度快照生成完成
- **THEN** 系统识别：已掌握节点的最远后代（学到哪）、薄弱节点（需补漏）、未学且前置已满足的节点（下一个可学）

---

### Requirement: 学习路径生成
系统 SHALL 基于用户起点与训练目标，生成个性化的知识点学习路径。

#### Scenario: 路径生成
- **WHEN** 水平测试完成
- **THEN** 系统按前置 DAG 拓扑排序，跳过已掌握节点，保留薄弱节点为补漏点，生成 5-10 个未来知识点的路径预览

#### Scenario: 路径动态调整
- **WHEN** 用户在某个知识点连续 WA 3 次或 mastery 下降
- **THEN** 系统将该知识点标记为薄弱，在路径中插入补漏任务（知识卡片 + 针对性练习）

---

### Requirement: 智能推送引擎
系统 SHALL 根据学习路径、薄弱点和当前掌握度，主动推送当日任务。

#### Scenario: 当日任务生成
- **WHEN** 用户访问当日任务页或 Celery 每日任务触发
- **THEN** 系统生成当日任务卡片：
  - 1 个讲义（Lecture CARD 级）
  - 1 道模板题（cf_rating ≤ 训练目标下限）
  - 2 道应用题（cf_rating 在训练目标区间）
  - 1 道挑战题（cf_rating ≥ 训练目标上限，可选做）

#### Scenario: 路径式推送
- **WHEN** 用户完成当前知识点所有练习且 mastery ≥ 0.8
- **THEN** 系统解锁下一知识点，推送讲义 + 配套练习题

#### Scenario: 补漏式推送
- **WHEN** 用户在某个知识点连续出错 3 次
- **THEN** 系统诊断该知识点为薄弱项，推送对应知识卡片 + 针对性练习

#### Scenario: 推送题目查询逻辑
- **WHEN** 系统推荐题目
- **THEN** 查询 `ProblemKnowledgePoint` 关联的题目，按 cf_rating 升序，排除用户已 AC 的题目

---

### Requirement: 艾宾浩斯复习与模板肌肉记忆
系统 SHALL 基于遗忘曲线触发复习提醒，并增加算法模板的肌肉记忆训练。

#### Scenario: 知识点复习提醒
- **WHEN** 用户学习某个知识点后，经过 1天/2天/4天/7天/15天/30天 的遗忘临界点
- **THEN** 系统推送该知识点的复习卡片 + 一道变体复习题

#### Scenario: 模板肌肉记忆训练
- **WHEN** 用户学过含模板代码的知识点（如线段树/KMP/并查集）满 7 天
- **THEN** 系统推送模板默写任务，用户在平台内提交模板代码
- **AND** 系统通过单测比对验证模板正确性，未通过则重新进入默写队列

#### Scenario: 复习完成记录
- **WHEN** 用户完成复习题或模板默写
- **THEN** 系统更新该知识点的复习周期，并重置遗忘曲线计时

---

### Requirement: 学习进度追踪
系统 SHALL 记录用户的学习行为，提供可视化进度面板。

#### Scenario: 进度面板
- **WHEN** 用户查看个人进度
- **THEN** 系统展示：
  - 已完成知识点数 / 总题数 / 通过率 / 连续打卡天数
  - 各知识点掌握度雷达图
  - CF Rating 曲线（同步自 CF）
  - 训练目标完成进度

#### Scenario: 掌握度计算
- **WHEN** 系统更新某知识点的 mastery
- **THEN** 计算：mastery = AC 题数 / 该知识点关联题目总数
- **AND** 状态分级：
  - mastery ≥ 0.8 且 AC ≥ 3 → 已掌握
  - 0.5 ≤ mastery < 0.8 → 基本掌握
  - 0 < mastery < 0.5 → 薄弱
  - 无提交 → 未学

#### Scenario: 弱项诊断
- **WHEN** 系统分析用户做题数据
- **THEN** 自动识别薄弱知识点（mastery < 0.5），在进度面板中高亮

---

### Requirement: 错题本
系统 SHALL 自动收录用户在 CF 上的错题，并支持同类题推荐。

#### Scenario: 错题自动收录
- **WHEN** CF 同步任务拉到 verdict 为 WA/TLE/RE 的提交
- **THEN** 系统自动将该题加入错题本，标注错误类型与提交时间

#### Scenario: 同类题推荐
- **WHEN** 用户查看错题
- **THEN** 系统基于错题关联的知识点推荐 2-3 道同类变体题（按 cf_rating 升序，排除已 AC 题）

---

### Requirement: 组队系统
系统 SHALL 支持三人队伍的组建与训练进度共享。

#### Scenario: 创建队伍
- **WHEN** 用户发起组队
- **THEN** 系统创建队伍，生成邀请码，队长可分享给队友

#### Scenario: 加入队伍
- **WHEN** 用户输入邀请码
- **THEN** 系统将其加入对应队伍，每队上限 3 人

#### Scenario: 队伍训练进度共享
- **WHEN** 队员查看队伍面板
- **THEN** 系统展示：三人各自的学习路径进度、本周做题数、共享的错题本
- **AND** 支持队内分工标注（谁主攻 DP / 图论 / 字符串）

#### Scenario: 队伍权限边界
- **WHEN** 队员尝试修改队伍信息
- **THEN** 仅队长可修改队名、解散队伍；队员只能查看与退出

---

### Requirement: 模板代码库
系统 SHALL 为每个算法知识点提供标准模板代码（含注释），定位为学习辅助。

#### Scenario: 模板查阅
- **WHEN** 用户在学习或做题时请求模板
- **THEN** 系统展示该知识点的标准代码模板，支持一键复制

#### Scenario: 模板版权
- **WHEN** 录入模板代码
- **THEN** 模板必须为平台原创或公共领域，**不抄左程云 PPT 或其他版权材料**

---

### Requirement: 自建题库题解
系统 SHALL 为自建种子题库（source="platform"）提供题解功能，不为外链题目提供题解。

#### Scenario: 自建题目题解
- **WHEN** 用户完成一道自建题目（source="platform"）后发布题解
- **THEN** 题解公开可见，其他用户可点赞

#### Scenario: 外链题目无题解
- **WHEN** 用户查看 CF 外链题目
- **THEN** 系统不展示题解入口，引导用户去 CF 官方 tutorial 或大佬博客

#### Scenario: 精选题解
- **WHEN** 自建题目题解获得超过 10 个点赞
- **THEN** 系统标记为"精选题解"，优先展示
