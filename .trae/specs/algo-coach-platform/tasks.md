# Tasks

## Phase 1: 项目基础

- [ ] Task 1: 项目脚手架搭建
  - [ ] 1.1 初始化前端项目（React + TypeScript + Vite + TailwindCSS）
  - [ ] 1.2 初始化后端项目（Python FastAPI + PostgreSQL + SQLAlchemy）
  - [ ] 1.3 配置 Docker Compose 开发环境（PostgreSQL + Redis + 后端 + 前端）
  - [ ] 1.4 搭建项目目录结构与代码规范配置（ESLint, Prettier, Ruff）

- [x] Task 2: 用户认证与档案
  - [x] 2.1 实现用户注册/登录 API（JWT 认证）
  - [x] 2.2 实现 ACM 档案字段（学校、CF handle、AtCoder handle、目标奖牌梯度）
  - [x] 2.3 实现 CF handle 绑定与验证（调 CF API `user.info`）
  - [x] 2.4 构建登录/注册/个人中心前端页面

## Phase 2: 内容与知识库

- [ ] Task 4: 知识点体系
  - [ ] 4.1 设计知识点数据模型（含前置依赖关系、难度等级）
  - [ ] 4.2 实现知识点 CRUD 与管理 API
  - [ ] 4.3 实现知识点图谱展示（前端树形/DAG 可视化）
  - [ ] 4.4 解析 oi-wiki mkdocs.yml nav 树，按 ACM 剪枝标准生成种子数据（目标 ~200 节点）

- [ ] Task 5: 讲义与模板代码
  - [ ] 5.1 设计讲义数据模型（三级粒度：CARD / STANDARD / DEEP 题型专题）
  - [ ] 5.2 实现讲义 CRUD 与关联知识点 API
  - [ ] 5.3 实现模板代码库（关联知识点，平台原创或公共领域）
  - [ ] 5.4 构建讲义浏览与模板复制前端页面

- [ ] Task 6: RAG 知识库
  - [ ] 6.1 搭建 pgvector 向量数据库
  - [ ] 6.2 实现讲义内容切片与向量化入库 Pipeline
  - [ ] 6.3 接入国内 LLM 服务（DeepSeek / 通义 / 智谱），实现知识检索 + LLM 问答 API
  - [x] 6.4 实现 LLM 调用次数限制（每用户 20 次/天）
  - [ ] 6.5 构建 AI 问答前端界面（聊天式交互）

- [ ] Task 7: 题库管理
  - [ ] 7.1 设计题目数据模型（含四层来源：CF 外链 / 自建种子 / AtCoder 外链 / 用户自报）
  - [ ] 7.2 设计 ProblemKnowledgePoint 关联表（含 source 与 confidence 字段）
  - [ ] 7.3 实现自建题目 CRUD（含 AI 标注知识点）
  - [ ] 7.4 实现题目筛选与搜索 API（按知识点、难度、CF rating）
  - [ ] 7.5 构建题库浏览与筛选前端页面（CF 题目点击跳转外链）
  - [ ] 7.6 预置自建种子题库（500 题，1-2 周人工录入 + AI 标注 + 审核）

## Phase 3: CF 同步与水平测试

- [x] Task 8: Codeforces 数据同步
  - [x] 8.1 实现服务端 CF API 客户端（含速率限制 1 次/2 秒 + 指数退避）
  - [x] 8.2 实现 `problemset.problems` 每日全量同步任务（Celery）
  - [x] 8.3 实现 `user.status` 增量同步任务（每用户每 5 分钟一次）
  - [x] 8.4 实现 `user.rating` 每日同步任务
  - [x] 8.5 设计 Submission 表（只存元数据，不存源代码）

- [x] Task 9: 水平测试与冷启动
  - [x] 9.1 实现 CF 用户的冷启动逻辑（拉 user.status + cf_tags 映射 + mastery 计算）
  - [x] 9.2 实现未绑 CF 用户的诊断题测试（15 道覆盖 10 知识点）
  - [x] 9.3 实现起点定标算法（已学最远后代 / 薄弱节点 / 下一可学节点）
  - [x] 9.4 按 CF Rating 定训练目标（铜/银/金/高级）
  - [x] 9.5 构建水平测试引导流程前端页面

## Phase 4: 核心教学

- [x] Task 10: 学习路径与推送引擎
  - [x] 10.1 实现学习路径生成算法（前置 DAG 拓扑排序 + 跳过已掌握 + 保留补漏点）
  - [x] 10.2 实现路径动态调整（连续 WA 3 次插入补漏任务）
  - [x] 10.3 实现当日任务生成（1 讲义 + 1 模板题 + 2 应用题 + 1 挑战题）
  - [x] 10.4 实现推送题目查询逻辑（按 cf_rating 升序，排除已 AC）
  - [x] 10.5 构建当日任务卡片前端页面

- [ ] Task 11: 学习进度与掌握度
  - [ ] 11.1 设计学习记录数据模型（知识点 mastery、打卡记录）
  - [x] 11.2 实现掌握度计算（mastery = AC 题数 / 关联题目总数）
  - [x] 11.3 实现进度面板 API（已完成知识点数 / 通过率 / 打卡 / 雷达图 / Rating 曲线）
  - [x] 11.4 实现弱项诊断（mastery < 0.5 自动标记）
  - [x] 11.5 构建个人进度面板前端页面

- [x] Task 12: 错题本
  - [x] 12.1 实现错题自动收录（CF 同步到 WA/TLE/RE 时触发）
  - [x] 12.2 实现错题本列表与详情 API
  - [x] 12.3 实现同类题推荐（基于知识点关联 + cf_rating 升序）
  - [x] 12.4 构建错题本前端页面

## Phase 5: 复习与组队

- [ ] Task 13: 艾宾浩斯复习与模板肌肉记忆
  - [ ] 13.1 设计复习记录数据模型（学习时间、复习周期、遗忘曲线阶段）
  - [ ] 13.2 实现遗忘临界点计算（1d/2d/4d/7d/15d/30d）
  - [ ] 13.3 实现 Celery 定时复习提醒任务
  - [ ] 13.4 实现模板默写任务（含单测比对验证）
  - [ ] 13.5 构建复习提醒前端组件

- [ ] Task 14: 组队系统
  - [ ] 14.1 设计队伍数据模型（Team 表、邀请码、三人上限）
  - [ ] 14.2 实现队伍 CRUD 与邀请码加入 API
  - [ ] 14.3 实现队伍训练进度共享 API（三人路径进度、本周做题数、共享错题本）
  - [ ] 14.4 实现队内分工标注（谁主攻 DP / 图论 / 字符串）
  - [ ] 14.5 构建队伍面板前端页面

## Phase 6: 自建题库题解

- [ ] Task 15: 自建题库题解
  - [ ] 15.1 实现自建题目题解发布/编辑/删除 API（限制 source="platform"）
  - [ ] 15.2 实现题解点赞 API
  - [ ] 15.3 实现精选题解自动标记（点赞 ≥ 10）
  - [ ] 15.4 构建自建题目题解详情前端页面

# Task Dependencies
- Task 2 依赖 Task 1
- Task 5 依赖 Task 4
- Task 6 依赖 Task 5
- Task 7 依赖 Task 4
- Task 8 依赖 Task 2（CF handle 绑定）+ Task 7（Problem 表）
- Task 9 依赖 Task 7 + Task 8
- Task 10 依赖 Task 9
- Task 11 依赖 Task 8（同步数据才能算 mastery）
- Task 12 依赖 Task 8 + Task 11
- Task 13 依赖 Task 11
- Task 14 依赖 Task 2 + Task 11
- Task 15 依赖 Task 7（自建题目）
