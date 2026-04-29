r"""
文件位置: app/tasks/heartbeat_flush.py
文件名称: heartbeat_flush.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.1
功能说明:
    Celery 定时任务：将 Redis 心跳缓冲批量落库到 PostgreSQL。

    调度频率：每 30 秒执行一次（D2 决策）

    执行逻辑：
      1. 从主库查询所有激活中的游戏项目
      2. 对每个游戏项目，扫描 Redis 中的 device:runtime:{game_id}:* 键
      3. 将扫描到的设备数据批量 UPSERT 到对应游戏库的 device_runtime 表
         ON CONFLICT (device_id) DO UPDATE — 只保留最新状态，不插入重复行
      4. 单个游戏项目失败不影响其他项目继续落库

    Windows 开发环境启动：
      Worker: celery -A app.core.celery_app worker --pool=solo --loglevel=info
      Beat:   celery -A app.core.celery_app beat --loglevel=info

    性能估算（D2 决策参数）：
      10,000 台设备 × 每 30 秒上报一次 ≈ 333 req/s 写 Redis
      Celery 每 30 秒批量 UPSERT ≈ 10,000 行/次 → PostgreSQL 约 167 行/秒

关联文档:
    [[01-网络验证系统/Redis心跳落库策略]]

改进历史:
    V1.0.1 - 所有 DB 操作改用 NullPool 引擎，修复 asyncio.run() 关闭事件循环后
             连接池失效导致的 'Event loop is closed' / 'NoneType.send' 错误；
             Redis 客户端改为任务内按需创建，不复用模块级连接池；
             _upsert_to_game_db 改用 project.db_name 构造 URL，
             修复 DATABASE_GAME_PREFIX 拼接导致库名重复（hive_game_game_001）问题
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
    任务执行失败时查看 Celery Worker 日志；落库异常单独记录，不影响下次执行。
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.config import settings
from app.models.game.models import DeviceRuntime
from app.models.main.models import GameProject

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 任务专用引擎工厂（NullPool）
# ─────────────────────────────────────────────────────────────

def _make_task_engine(url: str):
    """
    为 Celery 任务创建无连接池引擎（NullPool）。

    为什么必须用 NullPool：
      asyncio.run() 每次执行都会创建并销毁一个事件循环。
      普通连接池（QueuePool）缓存的 asyncpg 连接绑定到被销毁的旧循环，
      下次任务执行时连接 ping 失败，报 'Event loop is closed' / 'NoneType.send'。
      NullPool 不缓存连接，每次查询建立新连接、用完立即关闭，完全规避此问题。
      代价：每次任务执行多一次 TCP 握手，在 30s 间隔的定时任务中可以接受。
    """
    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"ssl": False},
    )


# ─────────────────────────────────────────────────────────────
# Celery 任务入口（同步包装器）
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.heartbeat_flush.flush_device_heartbeats",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def flush_device_heartbeats(self) -> dict:
    """
    同步入口，通过 asyncio.run() 调用异步落库逻辑。
    Celery Worker 进程没有运行中的事件循环，asyncio.run() 是安全的。
    """
    try:
        result = asyncio.run(_async_flush_all())
        logger.info(
            f"[heartbeat_flush] 落库完成 | 游戏项目数={result['projects']} "
            f"总设备数={result['total_devices']} 耗时={result['elapsed_ms']}ms"
        )
        return result
    except Exception as exc:
        logger.error(f"[heartbeat_flush] 任务失败: {exc}", exc_info=True)
        # 自动重试，最多 3 次，间隔 10 秒
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
# 异步落库逻辑
# ─────────────────────────────────────────────────────────────

async def _async_flush_all() -> dict:
    """
    遍历所有激活游戏项目，逐一将 Redis 心跳数据批量落库。
    单个项目失败时记录日志并继续，不中断整体任务。

    Redis 客户端在此处按需创建（不复用模块级连接池），
    避免连接池绑定到已销毁事件循环的问题。
    """
    import redis.asyncio as aioredis
    from app.core.redis_client import get_all_heartbeats_for_game

    start_ms = _now_ms()
    # 每次任务创建独立 Redis 客户端，不依赖模块级连接池
    redis_client = aioredis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    total_devices = 0

    try:
        projects = await _get_active_projects()

        for project in projects:
            try:
                count = await _flush_one_project(redis_client, project)
                total_devices += count
            except Exception as exc:
                logger.error(
                    f"[heartbeat_flush] 项目 {project.code_name} 落库失败: {exc}",
                    exc_info=True,
                )

        return {
            "projects": len(projects),
            "total_devices": total_devices,
            "elapsed_ms": _now_ms() - start_ms,
        }
    finally:
        await redis_client.aclose()


async def _get_active_projects() -> list[GameProject]:
    """
    从主库查询所有激活中的游戏项目。
    使用 NullPool 引擎，避免连接池跨事件循环失效。
    """
    engine = _make_task_engine(settings.DATABASE_MAIN_URL)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            result = await session.execute(
                select(GameProject).where(GameProject.is_active == True)
            )
            # scalars().all() 在 session 关闭前调用，确保数据已加载
            return result.scalars().all()
    finally:
        await engine.dispose()


async def _flush_one_project(redis, project: GameProject) -> int:
    """
    将单个游戏项目的 Redis 心跳数据批量 UPSERT 到游戏库。
    返回处理的设备数量。
    使用 project.db_name 构造游戏库连接 URL，避免 code_name 前缀重复问题。
    """
    from app.core.redis_client import get_all_heartbeats_for_game
    heartbeats = await get_all_heartbeats_for_game(redis, project.id)
    if not heartbeats:
        return 0

    records = _build_upsert_records(heartbeats)
    if not records:
        return 0

    await _upsert_to_game_db(project.db_name, records)
    return len(records)


def _build_upsert_records(heartbeats: list[dict]) -> list[dict]:
    """
    将 Redis 心跳数据转换为 device_runtime 表的 UPSERT 记录。
    过滤掉数据不完整的心跳（user_id 缺失等）。
    """
    now = datetime.now(timezone.utc)
    records = []

    for hb in heartbeats:
        data = hb.get("data", {})
        user_id = hb.get("user_id") or data.get("user_id")
        device_fp = hb.get("device_fp")

        if not user_id or not device_fp:
            # 数据不完整，跳过（通常不应出现，属防御性检查）
            logger.warning(f"[heartbeat_flush] 跳过不完整心跳: {hb}")
            continue

        last_seen_ts = data.get("last_seen", 0)
        records.append({
            "device_id": device_fp,
            "user_id": int(user_id),
            "status": data.get("status"),
            "last_seen": (
                datetime.fromtimestamp(last_seen_ts, tz=timezone.utc)
                if last_seen_ts else now
            ),
            "game_data": data.get("game_data", {}),
            "updated_at": now,
        })

    return records


async def _upsert_to_game_db(db_name: str, records: list[dict]) -> None:
    """
    对游戏库执行批量 UPSERT。
    ON CONFLICT (device_id) DO UPDATE：同一设备只保留最新数据，不产生重复行。

    参数使用 db_name（如 hive_game_001）而非 code_name（如 game_001），
    避免 DATABASE_GAME_PREFIX 拼接导致库名重复（hive_game_game_001）。
    使用 NullPool 引擎，避免连接池跨事件循环失效。
    """
    from sqlalchemy.engine import make_url
    game_url = make_url(settings.DATABASE_MAIN_URL).set(database=db_name)
    engine = _make_task_engine(game_url)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            stmt = pg_insert(DeviceRuntime).values(records)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["device_id"],
                set_={
                    "status": stmt.excluded.status,
                    "last_seen": stmt.excluded.last_seen,
                    "game_data": stmt.excluded.game_data,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(upsert_stmt)
            await session.commit()
    finally:
        await engine.dispose()


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────

def _now_ms() -> int:
    """返回当前时间的毫秒时间戳，用于统计任务耗时。"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)
