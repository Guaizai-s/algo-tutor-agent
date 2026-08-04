"""Codeforces 数据同步 (Task 8)。

子模块：
- client: CF API 客户端（httpx + Redis 限流 + 指数退避）
- sync: 同步服务（problemset.problems / user.status / user.rating）
"""
