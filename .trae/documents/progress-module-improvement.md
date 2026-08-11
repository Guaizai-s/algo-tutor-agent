# 学习进度模块完善计划

## 0. 设计原则：进度页 vs 今日学习

**今日学习** = 战术执行层（今天具体做什么：讲义 + 4 道题）
**学习进度** = 战略诊断层（整体学得怎么样、哪里薄弱）

进度页只做 **诊断 + 导航**，不生成任务、不推荐具体题目。所有"去做某事"的按钮都指向现有系统：
- 薄弱点 → 跳转到今日学习页（路径补漏会自然生成相关任务）
- 待复习 → 跳转到复习页
- 路径进度 → 跳转到路线图页

---

## 1. 当前状态分析

### 1.1 现有功能
- **进度概览 API** (`GET /api/v1/progress/overview`)：返回 4 个统计卡片数据 + 知识点掌握度列表 + Rating 曲线 + 训练目标进度 + 薄弱知识点 ID
- **前端展示**：4 个 stat card（已掌握 KP / 通过题目 / 通过率 / 连续打卡）、分类柱状图 + 可折叠列表视图、训练目标进度条
- **后端服务**：mastery 计算（AC 数/关联题目总数）、打卡系统、弱项诊断

### 1.2 核心问题诊断

进度模块当前是 **纯诊断型** 面板，缺乏 **处方型** 能力。用户看到数据后，不知道下一步该做什么。

| # | 问题 | 严重度 | 影响 |
|---|------|--------|------|
| 1 | **无导航能力** — 页面只展示数据，不告诉用户"下一步该去哪" | 高 | 用户看完页面后无法转化为学习行动 |
| 2 | **薄弱点不可见** — `weak_knowledge_ids` 已返回但前端未使用，薄弱知识点在列表中无视觉区分 | 高 | 用户不知道哪些知识点需要优先补 |
| 3 | **缺少复习集成** — 进度页与艾宾浩斯复习系统完全隔离，看不到"待复习项" | 高 | 用户可能遗忘已学知识点而不知 |
| 4 | **缺少时间趋势** — 没有"本周/本月学了什么"、没有学习活动日历 | 中 | 用户无法感知自己的进步趋势 |
| 5 | **训练目标进度失真** — `_build_target_progress` 用全部知识点作分母，不按 rating 区间筛选 | 中 | 进度条不反映真实目标进度 |
| 6 | **缺少学习路径感知** — 看不到自己当前在路径的哪个位置 | 中 | 用户不知道"学到哪了" |
| 7 | **mastery 无时间衰减** — 只计算 AC 比例，不区分最近做题 vs 很久以前做的 | 低 | 长期不练的知识点仍显示为"已掌握" |
| 8 | **mastery 无难度加权** — easy 和 hard 题 AC 贡献相同 | 低 | 掌握度不反映真实难度 |

---

## 2. 改进方案

### 2.1 前端：新增"导航卡片"区域（最优先）

**文件**: `frontend/src/pages/Progress.tsx`、`frontend/src/types/index.ts`、`frontend/src/utils/api.ts`

**当前问题**: 页面是纯数据展示，看完不知道该去哪。

**改进**: 在 stat cards 下方新增"下一步行动"卡片区域，包含 3 个子卡片，**只导航不生成任务**：

1. **薄弱点一览** — 展示前 3 个薄弱知识点（`weak_knowledge_ids` 匹配 `mastery_by_category`），每个显示 mastery 进度条，底部 "查看今日学习" 按钮跳转到 `/daily-task` 页（路径补漏机制会自动生成薄弱点的补漏任务）
2. **待复习提醒** — 调用 `GET /api/v1/review/status` 获取到期复习项数量，显示"X 个知识点待复习"，底部 "去复习" 按钮跳转到 `/review` 页
3. **学习路径进度** — 调用 `GET /api/v1/learning-paths/current` 获取当前路径，显示"第 X/Y 步 - 知识点名称"，底部 "查看路线图" 按钮跳转到 `/roadmap` 页

**实现要点**:
- 前端新增 `reviewApi.getStatus()` 和 `learningApi.getCurrentPath(DEV_USER_ID)` 调用
- 3 个卡片横向排列（`grid-cols-3`），每个卡片内：标题 + 数据 + 导航按钮
- 薄弱点卡片：按 mastery 升序取前 3 个知识点名称，每个显示 mastery 百分比
- 复习卡片：显示 `due_count` / `total_records`
- 路径卡片：显示当前位置 + 进度百分比

### 2.2 前端：薄弱知识点视觉增强

**文件**: `frontend/src/pages/Progress.tsx`

**改进**: 在列表视图和柱状图中，薄弱知识点（`weak_knowledge_ids` 包含该项）视觉上突出显示：
- 进度条左侧添加红色圆点标记 `●`
- 进度条使用 `ring-1 ring-red-200` 边框
- 名称文字颜色加深

**实现要点**:
- 利用 `progress.weak_knowledge_ids` 构建 Set 判断是否为薄弱点
- 薄弱项的进度条容器添加 `ring-1 ring-red-200 bg-red-50` 样式

### 2.3 后端：progress overview 增加复习状态字段

**文件**: `backend/app/schemas/progress.py`、`backend/app/services/progress.py`

**改进**: 在 `ProgressOverviewResponse` 中新增 `review_status` 字段，包含到期复习数。在 `get_progress_overview` 中调用 `review.get_review_status`（只读调用，不修改 Role B 领地代码）。

**实现要点**:
- 新增 `ReviewStatus` schema：`{ due_count: int, total_records: int, completed: int }`
- `ProgressOverviewResponse` 增加 `review_status: ReviewStatus | None = None`
- `get_progress_overview` 中调用 `review.get_review_status(db, user_id)` 填充

### 2.4 后端：修复训练目标进度计算

**文件**: `backend/app/services/progress.py` (`_build_target_progress` 函数)

**改进**: 不再用全部知识点作分母，改为统计关联了 rating 在 `[target_rating_min, target_rating_max]` 区间内题目的知识点数量。

**实现要点**:
```python
# 统计关联了目标 rating 区间已发布题目的知识点数
total_in_range = (
    await db.execute(
        select(func.count(func.distinct(ProblemKnowledgePoint.knowledge_id)))
        .join(Problem, Problem.id == ProblemKnowledgePoint.problem_id)
        .where(
            Problem.status == ProblemStatus.PUBLISHED,
            Problem.cf_rating >= profile.target_rating_min,
            Problem.cf_rating <= profile.target_rating_max,
        )
    )
).scalar_one()
```

### 2.5 后端：新增学习活动数据端点

**文件**: `backend/app/routers/progress.py`、`backend/app/services/progress.py`、`backend/app/schemas/progress.py`

**改进**: 新增 `GET /progress/activity` 端点，查询近 30 天每日提交数（基于 `Submission` 表，Role B 领地，只读查询）。

**返回格式**:
```json
{
  "days": [{"date": "2026-08-01", "count": 5}, ...],
  "total_week": 12,
  "total_last_week": 8
}
```

### 2.6 前端：新增学习活动日历

**文件**: `frontend/src/pages/Progress.tsx`

**改进**: 在知识点掌握度下方新增"学习活动"区域，展示近 7 天每日做题数柱状图（CSS 实现，不引入新依赖）。

### 2.7 前端：学习路径进度条

**文件**: `frontend/src/pages/Progress.tsx`

**改进**: 在训练目标进度下方展示学习路径进度条（已完成/进行中/待解锁），数据来自 `learningApi.getCurrentPath(DEV_USER_ID)`。

---

## 3. 实施步骤

| 步骤 | 内容 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| 1 | 后端：修复训练目标进度计算 | `services/progress.py` | 高 |
| 2 | 后端：新增 review_status 到 overview | `schemas/progress.py`, `services/progress.py` | 高 |
| 3 | 前端：新增"导航卡片"区域 | `pages/Progress.tsx`, `types/index.ts`, `utils/api.ts` | 高 |
| 4 | 前端：薄弱知识点视觉增强 | `pages/Progress.tsx` | 高 |
| 5 | 后端：新增活动数据端点 | `routers/progress.py`, `services/progress.py`, `schemas/progress.py` | 中 |
| 6 | 前端：学习活动日历 | `pages/Progress.tsx` | 中 |
| 7 | 前端：学习路径进度条 | `pages/Progress.tsx` | 中 |

---

## 4. 验证步骤

1. **后端 lint**: `cd backend && ruff check .`
2. **前端 typecheck**: `cd frontend && npm run typecheck`
3. **前端 lint**: `cd frontend && npm run lint`
4. **功能验证**: 启动服务后访问进度页，确认：
   - 导航卡片区域显示薄弱点、待复习、路径进度
   - 薄弱知识点在列表中有红色标记
   - 训练目标进度条数值合理（按 rating 区间筛选后）
   - 学习活动日历显示近 7 天数据

## 5. 不纳入本次的范围

- mastery 时间衰减算法（需要额外数据建模，复杂度高）
- mastery 难度加权（需要定义权重体系，暂不引入）
- 完整的 gamification 系统（XP/等级/成就）
- 组队进度共享（spec 中规划但未实现）