# 个性化讲义体系方案

## 概述

将 algo-tutor 从"OI-Wiki 内容聚合器"升级为"独家个性化算法教练"，分三个阶段实施：
1. **Phase 1**: AI 改写 + 多源融合 → 独家静态讲义库
2. **Phase 2**: AI 动态生成 → 千人千面个性化讲义
3. **Phase 3**: 互动式自适应 → 渐进展开 + 内嵌测验 + 自适应深度

---

## 当前状态分析

### 讲义数据来源
- **OI-Wiki**: 原始 Markdown，风格偏学术文档
- **左程云讲义**: 从 PPTX/PDF 提取，内容碎片化
- 两源通过 `MERGE_KEYWORDS` 合并到同一知识点，但内容各自独立
- 灌库脚本: `backend/scripts/seed_knowledge_graph.py`

### 讲义数据模型
- `Lecture` 表: `knowledge_id`, `level` (CARD/STANDARD/DEEP — 静态内容时代的遗留设计，新体系不再依赖), `title`, `content`
- 无来源标记、无个性化字段、无用户关联
- 所有用户看到的同一知识点讲义完全相同
- **问题**: `LectureLevel` 三级分类在 AI 个性化生成体系下是多余的——深度应由 LLM 根据用户状态动态控制，而非预先分档

### 现有个性化基础设施（可复用）
- `UserKnowledgeState`: 用户-知识点掌握度 (mastery, is_weak, consecutive_wa)
- `LearningProfile`: 用户训练目标 rating 区间 (target_rating_min / target_rating_max)
- `UserProblemAC`: 用户已 AC 题目列表
- `DailyTask` + `DailyTaskItem`: 每日任务生成（已有 `lecture_card` 槽位）
- `TutorAgent`: 已有 OpenAI 调用能力，`search_knowledge` tool
- `ReviewRecord`: 艾宾浩斯复习记录

### 前端渲染管线
- `KnowledgeDetail.tsx`: ReactMarkdown + Shiki 代码高亮 + rehype-katex + rehype-raw
- 支持 admonition 预处理、代码块高亮、数学公式
- 讲义内容通过 `/knowledge/{kp_id}/lectures` API 获取

---

## Phase 1: AI 改写 + 多源融合（独家静态讲义库）

### 目标
用 LLM 对 OI-Wiki + 左程云内容进行统一改写，生成一套风格统一、带有"算法教练"品牌调性的独家讲义库。所有用户看到同一套，但比 OI-Wiki 原版更独家。

### 技术方案

#### 1.1 数据模型变更

**`backend/app/models/knowledge.py`** — Lecture 模型新增字段：

```python
class LectureSource(StrEnum):
    OI_WIKI = "oi_wiki"
    ZUO_LECTURE = "zuo_lecture"
    AI_GENERATED = "ai_generated"       # Phase 2 动态生成
    AI_REWRITTEN = "ai_rewritten"       # Phase 1 批量改写

class Lecture(UUIDMixin, TimestampMixin, Base):
    # ... 现有字段 ...
    source: Mapped[LectureSource] = mapped_column(
        SAEnum(LectureSource, ...),
        nullable=False,
        default=LectureSource.OI_WIKI,
    )
    source_lecture_id: Mapped[UUID | None] = mapped_column(
        PGUUID, ForeignKey("lectures.id", ondelete="SET NULL"), nullable=True
    )  # 指向原始讲义（改写场景）
    generation_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 改写元数据
    rewrite_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

#### 1.2 新增 AI 讲义生成服务

**`backend/app/services/lecture_generator.py`** — 新建文件：

- `generate_rewritten_lecture(kp: KnowledgePoint, sources: list[Lecture]) -> str`
  - 输入: 知识点的所有原始讲义（OI-Wiki + 左程云）
  - 用 OpenAI 改写为统一风格的独家讲义
  - System prompt 定义"算法教练"品牌调性：鼓励式、渐进式、实战导向
  - 输出格式: Markdown，包含：概念引入 → 核心原理 → 代码模板 → 复杂度分析 → 常见误区 → 练习题提示
  - 深度由 AI 根据知识点难度和内容量自行把握，不做 CARD/STANDARD/DEEP 分档

- `batch_rewrite_all(kp_ids: list[UUID]) -> int`
  - 批量改写所有知识点的讲义
  - 跳过已有 AI_REWRITTEN 且版本号最新的讲义（幂等）
  - 支持断点续传

#### 1.3 新增批量改写脚本

**`backend/scripts/rewrite_lectures.py`** — 新建文件：

```python
"""批量 AI 改写讲义脚本。
运行: docker compose exec backend python -m scripts.rewrite_lectures
选项:
  --kp-id UUID    只改写指定知识点
  --dry-run        预览不改写
  --force          强制覆盖已有改写
"""
```

#### 1.4 讲义改写 Prompt 设计

System prompt 关键要素：
- **品牌调性**: "你是算法教练平台的讲义编写专家..."
- **结构规范**: 概念引入 → 核心原理 → 图解/伪代码 → 代码模板(C++) → 复杂度分析 → 常见误区 → 关联题目
- **风格要求**: 口语化但不失严谨、鼓励式语气、多用"你"拉近距离
- **深度自适应**: 根据知识点本身的难度和内容量，AI 自行判断讲解深度，不做 CARD/STANDARD/DEEP 人为分档
- **内容约束**: 保留原内容的技术准确性，不编造算法细节

#### 1.5 Schema 变更

**`backend/app/schemas/knowledge.py`** — LectureRead 新增字段：

```python
class LectureRead(BaseSchema):
    # ... 现有字段 ...
    source: str  # "oi_wiki" | "zuo_lecture" | "ai_rewritten" | "ai_generated"
    rewrite_version: int = 1
```

#### 1.6 前端适配

**`frontend/src/types/index.ts`** — Lecture 类型新增 `source` 字段。

`KnowledgeDetail.tsx` 无需大改，讲义内容仍通过 ReactMarkdown 渲染，但可新增来源标签（如 "AI 精编" 角标）。

#### 1.7 数据库迁移

```bash
cd backend && alembic revision --autogenerate -m "add lecture source and rewrite fields"
```

### Phase 1 产出物
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/models/knowledge.py` | 修改 | Lecture 新增 source, source_lecture_id, rewrite_version |
| `backend/app/schemas/knowledge.py` | 修改 | LectureRead 新增 source, rewrite_version |
| `backend/app/services/lecture_generator.py` | 新建 | AI 讲义生成服务 |
| `backend/scripts/rewrite_lectures.py` | 新建 | 批量改写脚本 |
| `backend/alembic/versions/xxxx_add_lecture_source.py` | 新建 | 数据库迁移 |
| `frontend/src/types/index.ts` | 修改 | Lecture 类型新增 source |

---

## Phase 2: AI 动态生成（千人千面）

### 目标
在用户打开每日任务讲义时，由 LLM 根据其水平、错题历史、弱项、学习风格动态生成个性化讲义。同一知识点的不同用户看到不同内容。

### 技术方案

#### 2.1 数据模型变更

**`backend/app/models/learning.py`** — 新增个性化讲义缓存表：

```python
class PersonalizedLecture(UUIDMixin, TimestampMixin, Base):
    """用户个性化讲义缓存。"""
    __tablename__ = "personalized_lectures"
    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_id", name="uq_personalized_lecture"),
    )

    user_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False, index=True)
    knowledge_id: Mapped[UUID] = mapped_column(
        PGUUID, ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 上下文哈希：用于判断是否需要重新生成
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 生成时使用的上下文快照（调试/审计用）
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    knowledge: Mapped[KnowledgePoint] = relationship("KnowledgePoint")
```

#### 2.2 个性化讲义生成服务

**`backend/app/services/personalized_lecture.py`** — 新建文件：

- `get_or_generate(user_id, knowledge_id) -> PersonalizedLecture`
  - 查询缓存，若存在且 context_hash 未变则直接返回
  - 否则调用 LLM 生成新讲义，写入缓存
  - 深度由 AI 根据用户 mastery 动态控制，不做 level 分档

- `build_user_context(user_id, knowledge_id) -> dict`
  - 收集: 用户 mastery、is_weak、consecutive_wa
  - 收集: 用户错题列表（同一知识点）
  - 收集: 用户已 AC 题目列表
  - 收集: 用户学习画像 rating 区间
  - 收集: 前置知识点的掌握度
  - 生成 context_hash = SHA256(json(context))

- `generate_personalized(user_id, kp, level, context) -> str`
  - System prompt 融入用户上下文
  - 个性化要素:
    - 弱项知识点 → 放慢节奏、增加图解、补充基础回顾
    - 连续 WA → 加入"常见错误"专区、避坑提示
    - 已掌握前置 → 跳过前置知识回顾
    - rating 区间 → 调整例题难度引用
    - 错题相关 → 在讲义中关联用户错过的题目

#### 2.3 每日任务集成

**`backend/app/services/daily_tasks.py`** — 修改 `_pick_card_lecture`：

当前逻辑：从 `lectures` 表按 CARD → STANDARD → DEEP 优先级选讲义
新逻辑：
1. 优先查询 `personalized_lectures` 缓存
2. 若无缓存 → 调用 `get_or_generate()` 生成
3. 若 AI 生成失败 → 降级到 Phase 1 的 AI_REWRITTEN 静态讲义
4. 若静态讲义也无 → 降级到原始 OI-Wiki/左程云讲义（取任意一条，不再按 level 筛选）

**`backend/app/models/learning.py`** — DailyTaskItem 新增字段：

```python
class DailyTaskItem(UUIDMixin, TimestampMixin, Base):
    # ... 现有字段 ...
    personalized_lecture_id: Mapped[UUID | None] = mapped_column(
        PGUUID, ForeignKey("personalized_lectures.id", ondelete="SET NULL"), nullable=True
    )
```

#### 2.4 重新生成策略

以下情况触发重新生成（context_hash 变化）：
- 用户 mastery 变化超过 0.2
- 用户新增错题（同一知识点）
- 用户连续 WA 计数变化
- 用户 rating 区间变更
- 手动触发（API 参数 `?refresh=true`）

### Phase 2 产出物
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/models/learning.py` | 修改 | 新增 PersonalizedLecture 模型 + DailyTaskItem 新增字段 |
| `backend/app/services/personalized_lecture.py` | 新建 | 个性化讲义生成服务 |
| `backend/app/services/daily_tasks.py` | 修改 | _pick_card_lecture 集成个性化讲义 |
| `backend/app/routers/knowledge.py` | 修改 | 新增 GET /knowledge/{kp_id}/personalized-lecture |
| `backend/app/schemas/knowledge.py` | 修改 | 新增 PersonalizedLectureRead |
| `backend/alembic/versions/xxxx_personalized_lecture.py` | 新建 | 数据库迁移 |
| `frontend/src/types/index.ts` | 修改 | 新增 PersonalizedLecture 类型 |

---

## Phase 3: 互动式自适应讲义

### 目标
讲义不再是静态文本，而是互动式学习体验：渐进展开、内嵌小测验、根据答题表现动态调整展示深度。

### 技术方案

#### 3.1 讲义内容增强格式

定义一套扩展 Markdown 语法（兼容现有渲染管线）：

```
:::quiz{type="single" answer="B"}
在二叉搜索树中，删除一个有两个子节点的节点时，通常用什么节点替换？
A. 左子树的最大节点
B. 右子树的最小节点  
C. 父节点
D. 任意叶子节点
:::

:::progressive{title="进阶：红黑树的自平衡策略"}
<此处是高级内容，默认折叠>
:::

:::hint{trigger="wrong_quiz_1"}
你选的答案是左子树最大节点——这在某些场景下也可行，但标准做法是选右子树最小节点。
因为这样可以保持 BST 性质：右子树所有节点 > 被删除节点 > 左子树所有节点。
:::
```

#### 3.2 前端互动组件

**`frontend/src/components/lecture/`** — 新建目录：

- `QuizBlock.tsx`: 内嵌测验组件
  - 单选/多选/填空
  - 即时反馈（正确/错误 + 解释）
  - 提交结果到后端 `POST /lecture-interactions`
  
- `ProgressiveDisclosure.tsx`: 渐进展开组件
  - 默认折叠，点击展开
  - 展开状态持久化到 localStorage

- `AdaptiveHint.tsx`: 自适应提示组件
  - 根据用户之前的答题表现显示/隐藏提示
  - 弱项用户自动展开更多解释

- `LectureProgress.tsx`: 讲义阅读进度条
  - 追踪章节阅读进度
  - 上报到后端

#### 3.3 讲义互动追踪

**`backend/app/models/learning.py`** — 新增互动追踪表：

```python
class LectureInteraction(UUIDMixin, TimestampMixin, Base):
    """用户讲义互动记录。"""
    __tablename__ = "lecture_interactions"

    user_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False, index=True)
    lecture_id: Mapped[UUID] = mapped_column(
        PGUUID, ForeignKey("lectures.id", ondelete="CASCADE"), nullable=True
    )
    personalized_lecture_id: Mapped[UUID | None] = mapped_column(
        PGUUID, ForeignKey("personalized_lectures.id", ondelete="CASCADE"), nullable=True
    )
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # quiz_answer | section_view | time_spent | hint_requested | progressive_expand
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

**`backend/app/routers/knowledge.py`** — 新增端点：

```python
@router.post("/lectures/{lecture_id}/interactions")
async def record_lecture_interaction(...)
```

#### 3.4 自适应深度控制

在 `PersonalizedLecture` 生成时，根据用户状态标记推荐展示深度：

- `display_mode: "full"` — 全部展开（弱项用户）
- `display_mode: "compact"` — 折叠进阶部分（已掌握用户）
- `display_mode: "quiz_first"` — 先测验再决定展开深度（首次学习）

前端根据 `display_mode` 控制 ProgressiveDisclosure 的默认展开状态。

#### 3.5 Markdown 预处理扩展

**`frontend/src/pages/KnowledgeDetail.tsx`** — 新增预处理函数：

```typescript
function preprocessInteractive(md: string): string {
  // 将 :::quiz{...} 转为 <quiz-block data-answer="B">...</quiz-block>
  // 将 :::progressive{title="..."} 转为 <details class="progressive"><summary>...</summary>...</details>
  // 将 :::hint{...} 转为 <div class="adaptive-hint" data-trigger="...">...</div>
}
```

### Phase 3 产出物
| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/components/lecture/QuizBlock.tsx` | 新建 | 内嵌测验组件 |
| `frontend/src/components/lecture/ProgressiveDisclosure.tsx` | 新建 | 渐进展开组件 |
| `frontend/src/components/lecture/AdaptiveHint.tsx` | 新建 | 自适应提示组件 |
| `frontend/src/components/lecture/LectureProgress.tsx` | 新建 | 阅读进度条 |
| `frontend/src/pages/KnowledgeDetail.tsx` | 修改 | 集成互动组件、新增预处理函数 |
| `backend/app/models/learning.py` | 修改 | 新增 LectureInteraction 模型 |
| `backend/app/routers/knowledge.py` | 修改 | 新增互动记录端点 |
| `backend/app/schemas/knowledge.py` | 修改 | 新增 LectureInteraction Schema |
| `backend/alembic/versions/xxxx_lecture_interactions.py` | 新建 | 数据库迁移 |

---

## 实施路线图

```
Phase 1 (1-2 天)
├── 1.1 数据库迁移: Lecture 新增 source/rewrite_version
├── 1.2 lecture_generator.py 服务
├── 1.3 rewrite_lectures.py 批量脚本
├── 1.4 前端类型更新
└── 1.5 运行批量改写，验证质量

Phase 2 (2-3 天)
├── 2.1 数据库迁移: PersonalizedLecture 表
├── 2.2 personalized_lecture.py 服务
├── 2.3 daily_tasks.py 集成
├── 2.4 knowledge router 新端点
├── 2.5 前端个性化讲义展示
└── 2.6 端到端测试

Phase 3 (3-4 天)
├── 3.1 互动 Markdown 语法设计
├── 3.2 QuizBlock + ProgressiveDisclosure 组件
├── 3.3 预处理函数
├── 3.4 LectureInteraction 追踪
├── 3.5 自适应深度控制
└── 3.6 前端集成 + 测试
```

---

## 假设与决策

1. **LLM 成本**: 假设 OpenAI API 调用成本可接受。Phase 1 批量改写约 200+ 知识点，每知识点 1 次 API 调用；Phase 2 每次用户打开讲义 1 次调用（有缓存）。
2. **内容质量**: AI 改写后内容需人工抽检。关键知识点（如 DP、图论）优先改写并验证。
3. **缓存策略**: Phase 2 的个性化讲义缓存基于 context_hash，用户状态小幅变化不触发重新生成。
4. **降级策略**: 所有 AI 生成路径都有降级方案（AI 改写 → 原始 OI-Wiki），确保系统在 API 故障时仍可用。
5. **兼容性**: Phase 1 改写后的讲义仍为 Markdown 格式，完全兼容现有前端渲染管线。
6. **Role A 领地**: 所有改动均在 Role A 领地内（frontend + 后端内容侧），不涉及 Role B 的引擎侧模块。

---

## 验证步骤

### Phase 1 验证
```bash
# 1. 数据库迁移
cd backend && alembic upgrade head

# 2. 改写单个知识点测试
docker compose exec backend python -m scripts.rewrite_lectures --kp-id <uuid> --dry-run

# 3. 批量改写
docker compose exec backend python -m scripts.rewrite_lectures

# 4. 验证 API
curl http://localhost:8000/api/knowledge/<kp_id>/lectures | jq '.[] | {title, source}'

# 5. 前端验证
# 打开 http://localhost:5173/knowledge/<kp_id> 查看改写后讲义
```

### Phase 2 验证
```bash
# 1. 生成个性化讲义
curl -X POST http://localhost:8000/api/knowledge/<kp_id>/personalized-lecture \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<uuid>", "level": "card"}'

# 2. 验证每日任务集成
curl http://localhost:8000/api/learning/today?user_id=<uuid>

# 3. 前端验证
# 打开每日任务页面，查看讲义内容是否个性化
```

### Phase 3 验证
```bash
# 1. 前端组件测试
cd frontend && npm run typecheck && npm run lint

# 2. 互动记录 API
curl -X POST http://localhost:8000/api/knowledge/lectures/<id>/interactions \
  -d '{"user_id": "...", "interaction_type": "quiz_answer", "data": {"question": "q1", "answer": "B", "correct": true}}'

# 3. 浏览器验证
# 打开讲义页面，确认测验、渐进展开、自适应提示功能正常
```