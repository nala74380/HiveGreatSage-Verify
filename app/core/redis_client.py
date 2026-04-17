r"""
文件位置: app/core/redis_client.py
文件名称: redis_client.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    Redis 客户端封装，提供：
      1. 连接单例（get_redis FastAPI 依赖）
      2. Token 黑名单操作（revoke / is_revoked）
      3. Refresh Token 存储操作（store / get / delete）
      4. 设备心跳缓冲操作（set_heartbeat / get_heartbeat）
      5. 限流计数（incr_rate_limit）
    Key 规划与 API鉴权方案.md / 架构设计.md 保持一致。
改进历史: 无
调试信息:
    Redis 连接失败时检查 REDIS_URL 环境变量，以及 Redis 服务是否启动。
    WSL2 下 Redis 安装：sudo apt install redis-server && sudo service redis-server start
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

# ── 连接池（全局单例）─────────────────────────────────────────
_redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,      # 自动 bytes → str，省去到处 .decode()
    max_connections=50,
)


def get_redis_client() -> aioredis.Redis:
    """返回共享连接池的 Redis 客户端（非协程，直接调用）。"""
    return aioredis.Redis(connection_pool=_redis_pool)


async def get_redis() -> AsyncGenerator[aioredis.Redis, Any]:
    """
    FastAPI 依赖注入：获取 Redis 客户端。

    用法：
        @router.post("/login")
        async def login(redis: aioredis.Redis = Depends(get_redis)):
            ...
    """
    client = get_redis_client()
    try:
        yield client
    finally:
        # 连接池模式下 close() 只是归还连接，不关闭池
        await client.aclose()


# ── Token 黑名单操作 ──────────────────────────────────────────
# Key 格式：token:blacklist:{jti}，Value："revoked"，TTL = AT 剩余有效期

async def revoke_token(redis: aioredis.Redis, jti: str, ttl_seconds: int) -> None:
    """将 Access Token 的 jti 加入黑名单（用于登出或强制下线）。"""
    if ttl_seconds > 0:
        await redis.setex(f"token:blacklist:{jti}", ttl_seconds, "revoked")


async def is_token_revoked(redis: aioredis.Redis, jti: str) -> bool:
    """检查 Access Token 是否已被吊销（在黑名单中）。"""
    return await redis.exists(f"token:blacklist:{jti}") == 1


# ── Refresh Token 存储操作 ────────────────────────────────────
# Key 格式：refresh:{user_id}:{jti}，Value：JSON 字符串，TTL = 7天

async def store_refresh_token(
    redis: aioredis.Redis,
    user_id: int,
    jti: str,
    rt_value: str,
    device_fingerprint: str | None,
    ttl_seconds: int,
) -> None:
    """
    将 Refresh Token 存入 Redis。
    jti 是关联的 Access Token 的 jti，用于两者联动吊销。
    """
    data = json.dumps({
        "rt_value": rt_value,
        "user_id": user_id,
        "jti": jti,
        "device_fingerprint": device_fingerprint,
    })
    await redis.setex(f"refresh:{user_id}:{jti}", ttl_seconds, data)


async def get_refresh_token(
    redis: aioredis.Redis,
    user_id: int,
    jti: str,
) -> dict | None:
    """获取 Refresh Token 数据，不存在则返回 None。"""
    raw = await redis.get(f"refresh:{user_id}:{jti}")
    if raw is None:
        return None
    return json.loads(raw)


async def delete_refresh_token(
    redis: aioredis.Redis,
    user_id: int,
    jti: str,
) -> None:
    """删除 Refresh Token（登出时调用）。"""
    await redis.delete(f"refresh:{user_id}:{jti}")


async def delete_all_refresh_tokens(
    redis: aioredis.Redis,
    user_id: int,
) -> int:
    """
    删除指定用户的所有 Refresh Token（踢出所有设备时调用）。
    返回删除的 key 数量。
    """
    pattern = f"refresh:{user_id}:*"
    keys = []
    async for key in redis.scan_iter(pattern):
        keys.append(key)
    if keys:
        return await redis.delete(*keys)
    return 0


# ── 设备心跳缓冲 ──────────────────────────────────────────────
# Key 格式：device:runtime:{game_id}:{user_id}:{device_fp}
# TTL = 120 秒（2分钟超时视为离线，D2 决策：心跳30秒上报一次）

_HEARTBEAT_TTL = 120  # 秒


async def set_heartbeat(
    redis: aioredis.Redis,
    game_id: int,
    user_id: int,
    device_fp: str,
    payload: dict,
) -> None:
    """
    写入设备心跳数据到 Redis 缓冲层（不直接落库）。
    Celery 任务每 30 秒批量将缓冲区数据 UPSERT 到 PostgreSQL。
    """
    key = f"device:runtime:{game_id}:{user_id}:{device_fp}"
    await redis.setex(key, _HEARTBEAT_TTL, json.dumps(payload))


async def get_heartbeat(
    redis: aioredis.Redis,
    game_id: int,
    user_id: int,
    device_fp: str,
) -> dict | None:
    """获取单台设备的最新心跳数据（PC中控查询时优先走此路径）。"""
    key = f"device:runtime:{game_id}:{user_id}:{device_fp}"
    raw = await redis.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def get_all_heartbeats_for_game(
    redis: aioredis.Redis,
    game_id: int,
) -> list[dict]:
    """
    获取指定游戏的所有在线设备心跳数据（Celery 批量落库时调用）。
    返回列表，每项包含解析后的 payload。
    """
    pattern = f"device:runtime:{game_id}:*"
    results = []
    async for key in redis.scan_iter(pattern):
        raw = await redis.get(key)
        if raw:
            # 从 key 解析出 user_id 和 device_fp
            parts = key.split(":")
            # key 格式：device:runtime:{game_id}:{user_id}:{device_fp}
            if len(parts) >= 5:
                results.append({
                    "user_id": int(parts[3]),
                    "device_fp": parts[4],
                    "data": json.loads(raw),
                })
    return results


# ── 限流计数 ──────────────────────────────────────────────────
# Key 格式：ratelimit:{endpoint_tag}:{identifier}，TTL = 60 秒
# D5 决策：登录接口同IP每分钟≤10次；心跳同Token每分钟≤4次

async def incr_rate_limit(
    redis: aioredis.Redis,
    endpoint_tag: str,
    identifier: str,
    limit: int,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """
    滑动窗口限流（基于 Redis INCR + EXPIRE）。

    返回：(is_allowed: bool, current_count: int)
    endpoint_tag 示例：'login', 'heartbeat'
    identifier 示例：IP 地址 或 user_id
    """
    key = f"ratelimit:{endpoint_tag}:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        # 首次创建，设置过期时间
        await redis.expire(key, window_seconds)
    return count <= limit, count