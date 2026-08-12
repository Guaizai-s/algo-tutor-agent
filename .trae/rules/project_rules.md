# Project Rules

## 技术栈
- 前端: React 18 + TypeScript + Vite + TailwindCSS
- 后端: Python 3.12 + FastAPI + PostgreSQL + SQLAlchemy 2.0 (async)
- 详见: project_memory.md

## 开发模式（单人开发，AI 必读）

本项目为单人开发模式：**所有文件均可自由修改，无领地/角色划分**。
（原 Role A/B 分工已废弃，统一个开发者全栈负责前端 + 后端）

### 工作流程
1. **开始工作前**：`git pull` 拉取最新代码
2. **编写代码前**：先 `Read` 对应的 `backend/app/schemas/` 和 `spec.md`
3. **完成后**：`ruff check` / `npm run lint` → 提交 → 提 PR
4. **PR 合入后**：`git pull` 同步
5. **每个功能完成后必须提交**：每完成一个独立功能点就 commit 一次，不要攒多个功能一起提交。保持 commit 粒度小、可追溯。

### API 契约 = Schemas 目录
- 所有 API 的 Request/Response 类型定义在 `backend/app/schemas/`
- 后端实现路由前，先定义对应模块的 Schema 文件
- 前端已联调完成；新增接口时同步更新 Schema

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

### 任务完成即提交（必读）
- **每完成一个独立任务就立即 `git commit`**，不要攒多个任务一起提交。一个"任务" = 一个可独立验证的功能点 / 修复 / 改动，范围宁可小不可大。
- **commit 前必须跑 lint / typecheck 通过**：后端 `cd backend && ruff check .`，前端 `cd frontend && npm run lint && npm run typecheck`。未通过不得提交。
- **任务完成且校验通过后主动 commit**，不要等用户催促；用户未明确要求时也按此规则提交（除非用户另有限制）。
- **禁止把多个不相关任务塞进同一个 commit**；一次会话涉及多任务时，按任务边界拆成多个 commit，保持 commit 粒度小、可追溯。
- commit message 聚焦"为什么"，遵循仓库现有风格（参考 `git log`）。
- 按文件名精确添加文件，不 `git add -A`，避免误带 `.env` / 凭据 / 大文件。

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