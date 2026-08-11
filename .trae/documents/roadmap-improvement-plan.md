# 算法路线图改进计划

## 问题分析

当前"算法路线图"（`/knowledge` → `KnowledgeTree.tsx`）是一个**静态知识目录**，而不是一个有导向作用的"路线图"。具体问题：

### 1. 路线图 = 静态目录，无学习导向
- `KnowledgeTree.tsx` 仅展示 7 大分类下的知识点树，带讲义数和模板数徽章
- 没有任何"下一步该学什么"的引导
- 没有用户学习状态的展示（已掌握/学习中/未解锁）
- 用户可以浏览所有知识点，但不知道从哪里开始

### 2. 真正的学习路径被藏在"今日学习"页面
- 基于拓扑排序的个性化学习路径（`learning_path.py`）在 `/today` 页展示
- 仅以"学习路径预览"小 pills 形式呈现，信息密度极低
- 路径与路线图完全割裂：用户在路线图看不到推荐顺序，在今日学习看不到全局位置

### 3. 缺乏用户状态可视化
- 后端有 `UserKnowledgeState`（mastery, is_weak）、`LearningPathItem`（status: active/pending/done）
- 前端 KnowledgeTree 完全不使用这些数据，所有知识点一视同仁
- 用户不知道哪些已掌握、哪些正在学、哪些还未解锁

### 4. "路线图"名不副实
- 路线图（roadmap）的核心价值是**引导用户按正确顺序学习**
- 当前实现只是内容目录（catalog），没有任何引导能力

## 改进方案

### 核心思路：将学习路径数据融入路线图页面

在 KnowledgeTree 页面上叠加用户的学习状态，让知识点树变成一个真正的"进度路线图"：

1. 每个知识点节点显示其学习状态（done / active / pending / 未开始）
2. 高亮当前正在学习的知识点（active）
3. 已掌握的知识点标记为完成（done）
4. 前置未满足的知识点灰显（pending）
5. 在顶部显示推荐学习路径概览（前 N 个节点的拓扑序列）

### 具体改动

#### 1. 后端：新增"路线图视图"API

**文件**: `backend/app/routers/learning.py`（Role A 领地）

新增一个 API 端点，返回用户学习状态 + 知识点树聚合数据：

```
GET /api/v1/learning-paths/roadmap?user_id={uuid}
```

**响应结构**（在 `backend/app/schemas/learning.py` 新增）:

```python
class RoadmapKnowledgeNode(BaseSchema):
    id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    difficulty: str
    order: int
    lecture_count: int
    template_count: int
    # 学习状态
    status: str  # "done" | "active" | "pending" | "unlocked" | "none"
    mastery: float | None
    is_weak: bool
    path_position: int | None  # 在学习路径中的位置（仅 active 节点）

class RoadmapResponse(BaseSchema):
    user_id: UUID
    has_path: bool
    tree: list[RoadmapKnowledgeNode]  # 平铺列表，前端自行构建树
    path_preview: list[KnowledgePointRef]  # 拓扑排序前 N 个节点
```

**文件**: `backend/app/services/learning_path.py`（Role A 领地）

新增 `get_roadmap_data()` 函数：
- 加载所有知识点（同 `_load_dag`）
- 加载用户学习状态（`UserKnowledgeState`）
- 加载用户当前学习路径（`LearningPathItem`）
- 为每个知识点计算 status：done（mastery ≥ 0.8）/ active（路径中 status=active）/ pending（路径中 status=pending）/ unlocked（前置满足但未在路径中）/ none（前置未满足）
- 生成拓扑排序预览

#### 2. 前端：改造 KnowledgeTree 页面

**文件**: `frontend/src/pages/KnowledgeTree.tsx`

改动：
- 页面加载时同时调用 `knowledgeApi.getTree()` 和 `learningApi.getRoadmap(userId)`
- 将 learning state 合并到树节点中
- 每个节点根据状态显示不同样式：
  - **done（已掌握）**: 绿色勾 + 文字灰显，不可点击
  - **active（当前学习）**: 蓝色高亮 + 脉冲动画 + "当前"标签
  - **pending（未解锁）**: 灰色锁定图标 + 文字灰显
  - **unlocked（可学习）**: 正常显示，可点击
  - **none（前置未满足）**: 灰显 + 锁定图标
- 在页面顶部添加"推荐学习路径"横向时间线，显示前 8 个节点的拓扑顺序
- 统计卡片增加"已掌握 / 学习中"数据

**文件**: `frontend/src/utils/api.ts`

新增 API 调用：
```typescript
export const learningApi = {
  // ...existing...
  getRoadmap: (userId: string) =>
    api.get<RoadmapResponse>('/learning-paths/roadmap', { params: { user_id: userId } }),
}
```

**文件**: `frontend/src/types/index.ts`

新增类型：
```typescript
interface RoadmapKnowledgeNode {
  id: string
  name: string
  slug: string
  parent_id: string | null
  difficulty: string
  order: number
  lecture_count: number
  template_count: number
  status: 'done' | 'active' | 'pending' | 'unlocked' | 'none'
  mastery: number | null
  is_weak: boolean
  path_position: number | null
}

interface RoadmapResponse {
  user_id: string
  has_path: boolean
  tree: RoadmapKnowledgeNode[]
  path_preview: KnowledgePointRef[]
}
```

#### 3. 后端路由注册

**文件**: `backend/app/main.py`

如果新 API 在 `learning.py` 的 `path_router` 中（同一 prefix），无需额外注册。如果是独立路由，需在 main.py 中注册。

### 视觉设计要点

- 已掌握节点：绿色左边框 + 半透明背景 + ✅ 图标
- 当前学习节点：蓝色左边框 + 浅蓝背景 + 轻微脉冲动画
- 未解锁节点：灰色文字 + 🔒 图标 + 不可点击
- 学习路径时间线：页面顶部横向步骤条，done 绿色、active 蓝色、pending 灰色

### 状态计算逻辑

```
for each knowledge_point:
  if mastery >= 0.8 and not is_weak:
    status = "done"
  elif in learning_path and path_item.status == "active":
    status = "active"
  elif in learning_path and path_item.status == "pending":
    status = "pending"  
  elif all prerequisites are "done":
    status = "unlocked"
  else:
    status = "none"
```

## 验证步骤

1. 后端 lint: `cd backend && ruff check .`
2. 前端 typecheck: `cd frontend && npm run typecheck`
3. 前端 lint: `cd frontend && npm run lint`
4. 启动服务后访问 `/knowledge`，验证：
   - 无学习路径时，显示"请先生成学习路径"引导
   - 有学习路径时，各节点显示对应状态样式
   - 当前 active 节点高亮
   - 已掌握节点标记完成
   - 推荐路径时间线显示正确

## 注意事项

- 这是 Role A 领地改动（`backend/app/routers/learning.py`, `backend/app/services/learning_path.py`, `backend/app/schemas/learning.py`, `frontend/src/`）
- 不涉及 Role B 文件
- 新增 API 在 `learning-paths` 路由组下，与现有路径 API 一致
- 前端兼容无路径状态：首次访问时显示引导提示，不报错