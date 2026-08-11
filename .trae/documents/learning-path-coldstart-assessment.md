# 学习路径水平评估方案验证与推荐

## 背景

当前 `generate_learning_path()` 对新用户一律从零基础开始（所有 `UserKnowledgeState` 为空，mastery=0.0），无法根据用户已有水平跳过已掌握知识点。

---

## 四种方案验证结果

### 方案 1: 自评标记（路线图页加"我已掌握"按钮）

**改动范围：**

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 Schema | `backend/app/schemas/learning.py` | 新增 `MarkMasteredRequest` |
| 后端 Router | `backend/app/routers/learning.py` | 新增 `POST /learning-paths/mark-mastered` |
| 后端 Service | `backend/app/services/learning_path.py` | 新增 `mark_knowledge_mastered()` 函数 |
| 前端 API | `frontend/src/utils/api.ts` | 新增 `learningApi.markMastered()` |
| 前端页面 | `frontend/src/pages/KnowledgeTree.tsx` | 叶子节点旁加"已掌握"按钮，点击后刷新 |

**验证结论：✅ 可行**

- `PathItemStatus.SKIPPED = "skipped"` 已在模型定义中（`learning.py:114`，注释"已掌握，跳过"），但从未被使用
- `UserKnowledgeState` 表已存在，直接 upsert mastery=1.0 即可
- 前端知识树渲染逻辑清晰，叶子节点 `isClickable` 判断已存在，加按钮无冲突
- 改动量：约 60 行后端 + 40 行前端

**优点：** 改动最小，用户可以精确标记自己知道的知识点
**缺点：** 用户需要手动逐个标记，对大量已掌握知识点操作繁琐

---

### 方案 2: 入门测试（诊断题冷启动）

**改动范围：**

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 Service | `backend/app/services/coldstart.py` | `diagnostic_cold_start` 已存在，但缺少答题评分逻辑 |
| 后端 Router | `backend/app/routers/coldstart.py` | `POST /coldstart/diagnostic` 已存在 |
| 新增 | 诊断题答题评分逻辑 | 接受用户答案 → 判断 AC/WA → 计算 mastery |
| 前端 | 全新页面或弹窗 | 答题 UI + 进度条 + 结果展示 |

**验证结论：✅ 可行，但工作量最大**

- `diagnostic_cold_start()` 已实现选题逻辑（5 易 + 7 中 + 3 难，覆盖 10 个核心知识点），但**只选不评**
- 缺少：用户答题交互、判题、根据结果计算 mastery 的逻辑
- 需要新增整套答题流程
- 改动量：约 200+ 行后端 + 完整前端答题页

**优点：** 最客观，能真实反映用户水平
**缺点：** 工作量大，用户需要花时间做题

---

### 方案 3: Codeforces 账号同步（CF 冷启动）

**改动范围：**

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 Service | `backend/app/services/coldstart.py` | `cf_cold_start()` **已完整实现** |
| 后端 Router | `backend/app/routers/coldstart.py` | `POST /coldstart/cf` **已存在** |
| 后端 Service | `backend/app/services/learning_path.py` | `generate_learning_path()` 调用前先检查 coldstart 状态 |
| 前端 | `frontend/src/pages/KnowledgeTree.tsx` | 生成路径前先调用 coldstart，无 CF 则提示 |

**验证结论：✅ 已有完整实现，只需接入**

- `cf_cold_start()` 完整实现了：拉取 CF user.status → 映射 cf_tags 到知识点 → 计算 mastery → 写入 `UserKnowledgeState` → 设置 `LearningProfile` 训练目标 → 起点定标
- `POST /api/v1/coldstart/cf` 路由已存在
- `CF_TAG_TO_KNOWLEDGE_SLUG` 映射了 25 个 CF tag 到知识点 slug
- 唯一缺失：`generate_learning_path()` 生成路径前没有调 coldstart
- 改动量：约 30 行后端 + 20 行前端（调用 coldstart → 再生成路径）
- 若用户无 CF 账号或提交不足 20 条，降级到当前行为（从零开始）

**优点：** 已有完整实现，一键同步，客观准确
**缺点：** 仅对有 CF 账号且提交 ≥ 20 条的用户有效

---

### 方案 4: 快速跳过（路径时间线逐项跳过）

与方案 1 本质相同，但粒度更粗（只能从路径中跳，不能从知识树跳）。方案 1 已覆盖此能力。

**验证结论：** 不推荐单独实现，方案 1 更优。

---

## 推荐方案

**方案 3（CF 冷启动）→ 方案 1（自评标记）组合，分阶段实施：**

### 阶段 1：CF 冷启动接入（最小改动，立即见效）

1. 在 `KnowledgeTree.tsx` 的 `handleGeneratePath` 中，先调 `POST /coldstart/cf`，再调 `generatePath`
2. 若 CF 同步成功（mastered_count > 0），`generate_learning_path` 自动跳过已掌握节点
3. 若 CF 同步失败（无账号/提交不足），降级到当前行为，并在前端提示"未检测到 Codeforces 数据，将从零开始，你也可以手动标记已掌握的知识点"

### 阶段 2：自评标记（补充方案 1，覆盖无 CF 用户）

1. 后端新增 `POST /learning-paths/mark-mastered` 接口
2. 前端路线图叶子节点旁加"我已掌握"按钮
3. 利用已有的 `PathItemStatus.SKIPPED` 状态

---

## 改动文件清单

### 阶段 1（CF 冷启动接入）

| 文件 | 改动 |
|------|------|
| `frontend/src/utils/api.ts` | 新增 `coldstartApi.cfColdStart()` |
| `frontend/src/pages/KnowledgeTree.tsx` | `handleGeneratePath` 先调 coldstart 再调 generatePath |
| `backend/app/services/learning_path.py` | 无需改动（已有的 mastery 过滤逻辑自动生效） |

### 阶段 2（自评标记）

| 文件 | 改动 |
|------|------|
| `backend/app/schemas/learning.py` | 新增 `MarkMasteredRequest(knowledge_id: UUID)` |
| `backend/app/routers/learning.py` | 新增 `POST /learning-paths/mark-mastered` |
| `backend/app/services/learning_path.py` | 新增 `mark_knowledge_mastered()` 函数 |
| `frontend/src/utils/api.ts` | 新增 `learningApi.markMastered()` |
| `frontend/src/pages/KnowledgeTree.tsx` | 叶子节点加"已掌握"按钮 |

---

## 验证步骤

### 阶段 1
1. `ruff check` 后端通过
2. `npm run typecheck` 前端通过
3. 手动测试：绑定 CF 账号 → 点击"生成学习路径" → 验证已掌握节点被跳过

### 阶段 2
1. `ruff check` + `npm run typecheck` 通过
2. 手动测试：点击"我已掌握" → 节点变绿 → 重新生成路径后该节点被跳过