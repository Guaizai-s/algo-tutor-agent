# 算法教练平台 (Algo Tutor)

AI 驱动的算法学习平台，从"被动刷题"升级为"AI 教练主动教学"。

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 前端 | React 18 + TypeScript + Vite + TailwindCSS + React Router |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| 向量检索 | pgvector (PostgreSQL 扩展) |
| LLM | OpenAI API |
| 异步任务 | Celery |
| 判题沙箱 | Docker |
| 部署 | Docker Compose |

## 快速开始

### 环境要求

- Docker & Docker Compose
- Node.js 20+ (本地开发可选)
- Python 3.12+ (本地开发可选)

### 一键启动

1. 克隆项目
```bash
git clone <repo-url>
cd algo-tutor
```

2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY
```

3. 启动所有服务
```bash
docker compose up -d --build
```

4. 访问服务
- 前端: http://localhost:5173
- 后端 API 文档: http://localhost:8000/docs
- 后端 ReDoc: http://localhost:8000/redoc

### 评审黄金演示

```powershell
powershell -ExecutionPolicy Bypass -File scripts/reset-demo.ps1
```

随后在登录页点击“一键进入黄金演示账号”。完整的三分钟演示顺序、账号信息与讲解口径见 [DEMO.md](DEMO.md)。

### 本地开发（可选）

#### 后端
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 启动 PostgreSQL 和 Redis
docker compose up -d postgres redis

# 运行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

#### 前端
```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
algo-tutor/
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── components/      # 通用组件
│   │   ├── pages/           # 页面组件
│   │   ├── stores/          # Zustand 状态管理
│   │   └── utils/           # API 请求
│   └── package.json
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── schemas/         # Pydantic Schema (API 契约)
│   │   ├── routers/         # API 路由
│   │   ├── services/        # 业务逻辑
│   │   └── core/            # 配置、数据库、依赖注入
│   ├── alembic/             # 数据库迁移
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 核心功能模块

- **用户系统**: JWT 认证、角色管理（学员/教练/管理员）
- **小组协作**: 创建小组、邀请码加入、成员进度查看
- **知识点体系**: 图谱化知识点、前置依赖关系、三级粒度讲义
- **RAG 知识库**: 讲义向量化、语义检索、AI 问答带引用
- **题库系统**: 多难度题目、知识点标签、题目变体生成
- **在线判题**: Docker 沙箱隔离、多语言支持 (C++/Java/Python)、复杂度分析
- **智能反馈**: 渐进式提示、代码 Review、最优解对比
- **学习追踪**: 进度面板、雷达图、弱项诊断、错题本
- **复习系统**: 艾宾浩斯遗忘曲线、定时提醒
- **讨论社区**: 题解分享、点赞评论、精选标记
- **模拟面试**: 限时抽题、思路+编码、面试报告
- **激励机制**: 打卡、排行榜、成就徽章

## 数据库迁移

```bash
# 生成迁移文件
cd backend
alembic revision --autogenerate -m "描述变更内容"

# 执行迁移
alembic upgrade head

# 回滚上一个版本
alembic downgrade -1
```

## 代码规范

- 后端: Ruff (lint + format)
  ```bash
  cd backend && ruff check .
  cd backend && ruff format .
  ```
- 前端: ESLint + TypeScript
  ```bash
  cd frontend && npm run lint
  cd frontend && npm run typecheck
  ```

## 团队分工

| 角色 | 负责模块 |
|------|----------|
| A (后端核心) | 知识点、讲义、RAG、题库、题目变体、讨论区 |
| B (后端业务) | 认证、小组、判题、推送引擎、复习系统、模拟面试 |
| C (前端全栈) | 所有前端页面开发 |

## License

MIT
