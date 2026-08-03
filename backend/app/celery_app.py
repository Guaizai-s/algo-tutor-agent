"""Celery app 配置 (Task 8)。

- 使用 Redis 作为 broker 和 result backend
- beat schedule:
  - problemset.problems: 每日一次
  - user.status: 每 5 分钟一次
  - user.rating: 每日一次
- 单实例 beat 避免重复调度；数据库写入仍必须幂等
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "algo_tutor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.cf_tasks"],
)

# 配置：序列化用 JSON，单任务超时 10 分钟（CF API 可能很慢）
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # 任务执行完才 ack，避免 worker 崩溃丢任务
    worker_prefetch_multiplier=1,  # 一次只取一个任务，避免长任务阻塞
    task_time_limit=600,  # 10 分钟硬超时
    task_soft_time_limit=540,  # 9 分钟软超时
)

# Beat 调度表
# 注意：仅部署一个 beat 实例以避免重复调度；数据库写入仍必须幂等
celery_app.conf.beat_schedule = {
    "cf-sync-problemset-daily": {
        "task": "app.tasks.cf_tasks.sync_problemset_task",
        "schedule": crontab(hour=3, minute=0),  # 每日 03:00 执行
    },
    "cf-sync-user-status-5min": {
        "task": "app.tasks.cf_tasks.sync_all_users_status_task",
        "schedule": 300.0,  # 每 5 分钟
    },
    "cf-sync-user-rating-daily": {
        "task": "app.tasks.cf_tasks.sync_all_users_rating_task",
        "schedule": crontab(hour=4, minute=0),  # 每日 04:00 执行
    },
}


@celery_app.task(bind=True, name="app.tasks.cf_tasks.health_check")
def health_check(self) -> dict:  # type: ignore[no-untyped-def]
    """Celery 健康检查任务，用于启动检查。"""
    return {"status": "ok", "celery": True}
