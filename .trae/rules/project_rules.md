# Project Rules

## 技术栈
- 前端: React 18 + TypeScript + Vite + TailwindCSS
- 后端: Python 3.12 + FastAPI + PostgreSQL + SQLAlchemy 2.0 (async)
- 详见: project_memory.md

## 多人协作规则（AI 必读）

### 文件归属（不可跨区修改）
前端已完成，两人共同推进后端剩余模块，按"内容侧 / 引擎侧"切分。
（Role A 原为前端，维持前端维护 + 现有后端 + 内容侧；Role B 接引擎侧新模块）

```
# Role A 领地（前端维护 + 现有后端维护 + 知识点图谱维护 + 内容侧新模块）
# —— 前端维护
frontend/src/                       ← Role A（前端维护）
# —— 现有后端模块维护
backend/app/models/knowledge.py     ← Role A（含知识点图谱维护）
backend/app/models/problem.py       ← Role A
backend/app/routers/knowledge.py    ← Role A
backend/app/routers/problems.py     ← Role A
backend/app/routers/agent.py        ← Role A
backend/app/services/rag.py         ← Role A
backend/app/services/openai_service.py ← Role A
backend/app/agents/                 ← Role A
backend/app/tools/                  ← Role A
backend/app/core/                   ← Role A（基础设施：config/database）
# —— 内容侧新模块
backend/app/routers/discussions.py  ← Role A（Task 15 讨论区）
backend/app/routers/solutions.py    ← Role A（Task 15 题解）
backend/app/routers/progress.py     ← Role A（Task 10 进度）
backend/app/routers/wrongbook.py    ← Role A（Task 11 错题本）
backend/app/routers/submissions.py  ← Role A（提交记录查询）
backend/app/models/discussion.py    ← Role A（讨论区模型）
backend/app/services/discussion.py  ← Role A（讨论区业务）
backend/app/services/progress.py    ← Role A（进度业务）
backend/app/services/wrongbook.py   ← Role A（错题本业务）

# Role B 领地（引擎侧新模块：认证、判题、推送、复习）
backend/app/routers/auth.py         ← Role B（Task 2 认证）
backend/app/routers/judge.py        ← Role B（Task 8 判题）
backend/app/routers/notifications.py ← Role B（Task 12 推送/提醒）
backend/app/services/auth.py        ← Role B（认证业务）
backend/app/services/judge.py       ← Role B（判题沙箱）
backend/app/services/push.py        ← Role B（推送引擎）
backend/app/services/review.py      ← Role B（艾宾浩斯复习）
backend/app/models/user.py          ← Role B（用户模型）
backend/app/models/submission.py    ← Role B（提交记录模型，供 Role A 路由查询用）
backend/app/tasks/                  ← Role B（Celery 定时任务：复习提醒）

# 共享（API 契约，谁实现谁维护对应文件）
backend/app/schemas/                ← 各自维护自己模块的 schema 文件，可互读
backend/alembic/                    ← 生成迁移者负责，PR 协调
backend/app/main.py                 ← 谁新增 router 谁改，PR 协调
```

### 协作约定
- **提交记录(submission)**：Role B 建模型 + 判题写入；Role A 建查询路由。两端通过 schema 对接，PR 协调。
- **推送通知**：Role B 写推送引擎；Role A 的内容侧接口若需触发推送，调用 Role B 的 service，不直接改 push.py。
- **Celery 定时任务**：归 Role B，复习/推送相关任务在此；其他模块需异步任务时单独建文件、PR 协调。

### 工作流程
1. **开始工作前**：`git pull` 拉取最新代码
2. **编写代码前**：先 `Read` 对应的 `backend/app/schemas/` 和 `spec.md`
3. **只改自己领地的文件**，不要跨区修改
4. **完成后**：`ruff check` / `npm run lint` → 提交 → 提 PR
5. **PR 合入后**：通知其他人 `git pull`

### API 契约 = Schemas 目录
- 所有 API 的 Request/Response 类型定义在 `backend/app/schemas/`
- 后端实现路由前，先定义对应模块的 Schema 文件
- 前端已联调完成；新增接口由实现者同步更新 Schema 并通知前端（Role B）

## Lint & TypeCheck 命令
- 后端 lint: `cd backend && ruff check .`
- 后端 format: `cd backend && ruff format .`
- 前端 lint: `cd frontend && npm run lint`
- 前端 typecheck: `cd frontend && npm run typecheck`

## 启动命令
- 全部服务: `docker compose up -d`
- 仅后端: `cd backend && uvicorn app.main:app --reload --port 8000`
- 仅前端: `cd frontend && npm run dev`

## 数据库迁移
- 生成迁移: `cd backend && alembic revision --autogenerate -m "描述"`
- 执行迁移: `cd backend && alembic upgrade head`

## 目录结构
```
algo-tutor/
├── frontend/          # React SPA
├── backend/           # FastAPI
│   ├── app/
│   │   ├── models/    # SQLAlchemy 模型
│   │   ├── schemas/   # Pydantic Schema (API 契约)
│   │   ├── routers/   # API 路由
│   │   ├── services/  # 业务逻辑
│   │   └── core/      # 配置、依赖注入
│   └── alembic/       # 数据库迁移
├── docker-compose.yml
└── .trae/specs/       # Spec 文档
```

## AI 行为约定（必读）

### 提方案前必须验证，禁止纸面推理
- **提出技术方案前**，必须实际验证可行性（编译 / 测试 / 查文档 / 检查依赖），不可停留在"我觉得这个方案可行"。
- **替代方案同样适用**：当一个方案不可行而提出替代方案时，替代方案也必须先验证再回复。不要把未验证的替代方案丢给用户判断。
- **不可行的方案直接淘汰**：若替代方案验证后也不可行，直接告知"目前没有可行方案"，或继续提下一个并验证，不要让用户在多个不可行方案里挑。

### 验证方式（按场景选择）
- **代码/编译/测试类**：用 `RunCommand` 实际跑（如 `ruff check`、`npm run typecheck`、`pytest`），贴关键输出。
- **API/库版本类**：用 `WebSearch` 查官方文档确认 API 存在、参数正确、版本兼容。
- **现有代码冲突类**：用 `Read` / `Grep` 检查现有实现是否与新方案冲突。
- **类型/Lint 类**：用 `GetDiagnostics` 查 IDE 诊断信息。

### 验证过程要可见
- 回复时展示验证依据（命令输出、文档链接、引用的代码行），不要只说"我验证过了"。
- 若无法验证（如依赖外部服务、需要真实数据），明确标注"未验证，原因：xxx"，并说明需要什么条件才能验证。

### 反例（禁止）
- ❌ "方案 A 不可行，建议用方案 B" → 然后 B 也没验证，用户一跑发现 B 也不行。
- ❌ "这个库应该支持 xxx" → 没查文档，实际不支持。
- ❌ "这样改应该能编译" → 没跑 `ruff check` / `tsc`，实际有类型错误。

### 正例（鼓励）
- ✅ "方案 A 不可行（原因：xxx）。方案 B 已验证：`ruff check` 通过、`pytest` 3 passed，可使用。"
- ✅ "方案 B 经查 [官方文档](url) 确认 API 在 v2.0 已移除，改用方案 C：`tsc` 通过。"
- ✅ "无法验证：依赖 OpenAI API 真实调用，本地无 API key。建议你在 `.env` 配置后跑 `pytest tests/test_xxx.py` 验证。"