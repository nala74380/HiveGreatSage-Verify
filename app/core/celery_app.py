r"""
文件位置: app/core/celery_app.py
文件名称: celery_app.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.1
功能说明:
    Celery 应用实例，使用 Redis 作为 Broker 和 Result Backend。

    注册的定时任务：
      - flush_device_heartbeats : 每 30 秒执行，将 Redis 心跳缓冲批量落库

    Windows 开发环境启动命令（须在项目根目录执行）：
      Worker:  celery -A app.core.celery_app worker --pool=solo --loglevel=info
      Beat:    celery -A app.core.celery_app beat --loglevel=info
      两个命令需在两个独立终端中分别运行。

    Windows 使用 --pool=solo 原因：
      Windows 不支持 fork，默认的 prefork 池无法使用，solo 模式为单进程同步执行。

    生产环境（Linux/Docker）启动命令：
      celery -A app.core.celery_app worker --concurrency=4 --loglevel=info
      celery -A app.core.celery_app beat --loglevel=info

关联文档:
    [[01-网络验证系统/Redis心跳落库策略]]

改进历史:
    V1.0.1 (2026-04-27) - 新增 broker_connection_retry_on_startup /
                          worker_cancel_long_running_tasks_on_connection_loss
                          消除 CPendingDeprecationWarning，对齐 Celery 6.0 行为
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
    Broker 连接失败时检查 .env 中的 REDIS_URL 和 Redis 服务是否启动。
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401 - 备用，crontab 语法参考

from app.config import settings

celery_app = Celery(
    "hive_verify",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.heartbeat_flush"],  # 显式声明任务模块，避免自动发现失败
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 时区
    timezone="UTC",
    enable_utc=True,

    # 任务执行
    task_acks_late=True,                          # 任务执行完成后再 ACK，防止 Worker 崩溃丢任务
    task_reject_on_worker_lost=True,

    # Broker 连接重试策略（消除 CPendingDeprecationWarning，对齐 Celery 6.0 行为）
    # 启动时断线重试：True = 启动阶段也执行 broker_connection_retry 逻辑（Celery 6.0 默认值）
    broker_connection_retry_on_startup=True,
    # 连接丢失时取消长时任务：True = 连接断开后取消还未 ACK 的任务并重新入队（Celery 6.0 默认值）
    worker_cancel_long_running_tasks_on_connection_loss=True,

    # 定时任务（D2 决策：每 30 秒批量落库一次）
    beat_schedule={
        "flush-heartbeats-every-30s": {
            "task": "app.tasks.heartbeat_flush.flush_device_heartbeats",
            "schedule": 30.0,       # 每 30 秒执行一次
        },
    },

    # 结果过期时间（任务结果只保留 1 小时，心跳任务不需要长期保留结果）
    result_expires=3600,
)
