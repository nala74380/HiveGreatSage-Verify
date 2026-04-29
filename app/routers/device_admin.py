r"""
文件位置: app/routers/device_admin.py
名称: 管理后台设备监控路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V2.1.0
功能说明:
    T021 — 全局设备总览（Phase 2 已实现）：
      GET /admin/api/devices/
          在线状态双源判断：
            1. Redis SCAN device:runtime:*:{user_id}:{fp} 有数据 → 在线（实时）
            2. DeviceBinding.last_seen_at < 2分钟 → 在线（心跳每次更新该字段）
          game_data 优先取 Redis 最新值。

    T026 — 按游戏项目查询设备（已实现）：
      GET /admin/api/devices/{game_project_code}

改进历史:
    V2.1.0 (2026-04-28) - T021 双源在线判断（Redis+DB），心跳同步更新 last_seen_at
    V2.0.0 (2026-04-26) - T021 全局总览正式实现
    V1.0.1 (2026-04-26) - T021 占位返回 501
    V1.0.0 (2026-04-25) - T026 初始实现
"""

import json
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.core.security import decode_admin_token, decode_agent_token
from app.database import get_main_db
from app.models.main.models import Admin, Agent, DeviceBinding, User
from app.services.device_admin_service import (
    get_admin_device_list,
    get_agent_device_list,
)

router = APIRouter()
_http_bearer = HTTPBearer()

# 在线判定阈值（与 device_service._OFFLINE_THRESHOLD_SECONDS 保持一致）
_ONLINE_THRESHOLD = timedelta(seconds=90)


async def _get_admin_or_agent(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> tuple[Admin | None, Agent | None]:
    """解析 Admin 或 Agent Token，两者恰好有一个不为 None，否则返回 401。"""
    token = credentials.credentials

    try:
        payload = decode_admin_token(token)
        admin_id = int(payload["sub"])
        result = await db.execute(
            select(Admin).where(Admin.id == admin_id, Admin.status == "active")
        )
        admin = result.scalar_one_or_none()
        if admin:
            return admin, None
    except (JWTError, Exception):
        pass

    try:
        payload = decode_agent_token(token)
        agent_id = int(payload["sub"])
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.status == "active")
        )
        agent = result.scalar_one_or_none()
        if agent:
            return None, agent
    except (JWTError, Exception):
        pass

    raise HTTPException(
        status_code=http_status.HTTP_401_UNAUTHORIZED,
        detail="需要 Admin Token 或 Agent Token",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── T021 全局设备总览 ─────────────────────────────────────────

@router.get("/", summary="全平台设备总览（T021）")
async def list_all_devices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    online_only: bool = Query(default=False, description="只返回在线设备"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    全平台设备总览（T021）。

    在线判断双源策略（两者满足其一即视为在线）：
      1. Redis 中存在 device:runtime:*:{user_id}:{fp} 且 TTL 未过期 → 在线（实时最准）
      2. DeviceBinding.last_seen_at 在 90 秒内 → 在线（每次心跳都会更新该字段）

    Admin Token：全平台所有用户
    Agent Token：自己直接创建的用户（Phase 3 扩展为递归子树）
    """
    admin_caller, agent_caller = caller

    from loguru import logger
    logger.info(f"[list_all_devices] admin={admin_caller.username if admin_caller else None} agent={agent_caller.id if agent_caller else None} user_id_filter={user_id}")

    # 构建基础查询
    base_q = (
        select(DeviceBinding, User)
        .join(User, DeviceBinding.user_id == User.id)
        .where(DeviceBinding.status == "active")
    )
    if agent_caller is not None:
        base_q = base_q.where(User.created_by_agent_id == agent_caller.id)
    if user_id:
        base_q = base_q.where(DeviceBinding.user_id == user_id)

    # 总数（不分页）
    total = (await main_db.execute(
        select(func.count()).select_from(base_q.subquery())
    )).scalar_one()

    # 分页数据
    offset = (page - 1) * page_size
    rows_result = await main_db.execute(
        base_q
        .order_by(DeviceBinding.last_seen_at.desc().nullslast())
        .offset(offset).limit(page_size)
    )
    rows = rows_result.all()

    now = datetime.now(timezone.utc)
    devices = []
    page_online = 0

    for binding, user in rows:
        # ─── 1. 尝试从 Redis 读实时心跳 ─────────────────────────
        redis_data: dict | None = None
        # 管理员不知道 game_id，用通配符 SCAN
        # Key 格式：device:runtime:{game_id}:{user_id}:{device_fp}
        redis_pattern = f"device:runtime:*:{binding.user_id}:{binding.device_fingerprint}"
        async for rkey in redis.scan_iter(redis_pattern):
            raw = await redis.get(rkey)
            if raw:
                try:
                    redis_data = json.loads(raw)
                except Exception:
                    pass
            break  # 一台设备最多对应一个游戏，取第一条即可

        is_online_redis = redis_data is not None

        # ─── 2. DB 时间判断（心跳会更新 last_seen_at）────────────
        is_online_db = False
        if binding.last_seen_at:
            lsa = binding.last_seen_at
            if lsa.tzinfo is None:
                lsa = lsa.replace(tzinfo=timezone.utc)
            is_online_db = (now - lsa) <= _ONLINE_THRESHOLD

        is_online = is_online_redis or is_online_db

        if online_only and not is_online:
            continue
        if is_online:
            page_online += 1

        # game_data 优先 Redis
        game_data = None
        if redis_data:
            game_data = redis_data.get("game_data")

        # 状态值
        if redis_data and redis_data.get("status"):
            status_val = redis_data["status"]
        elif is_online:
            status_val = "idle"
        else:
            status_val = "offline"

        # last_seen 统一格式：ISO 字符串
        if redis_data and redis_data.get("last_seen"):
            try:
                last_seen_str = datetime.fromtimestamp(
                    int(redis_data["last_seen"]), tz=timezone.utc
                ).isoformat()
            except Exception:
                last_seen_str = binding.last_seen_at.isoformat() if binding.last_seen_at else None
        else:
            last_seen_str = binding.last_seen_at.isoformat() if binding.last_seen_at else None

        devices.append({
            "device_id":   binding.device_fingerprint,
            "user_id":     binding.user_id,
            "username":    user.username,
            "status":      status_val,
            "last_seen":   last_seen_str,
            "game_data":   game_data,
            "is_online":   is_online,
            "source":      "redis" if is_online_redis else "database",
        })

    # 全局在线数（用 DB 时间，不受分页影响，不做 Redis SCAN all）
    cutoff = now - _ONLINE_THRESHOLD
    online_count_q = (
        select(func.count(DeviceBinding.id))
        .join(User, DeviceBinding.user_id == User.id)
        .where(
            DeviceBinding.status == "active",
            DeviceBinding.last_seen_at >= cutoff,
        )
    )
    if agent_caller is not None:
        online_count_q = online_count_q.where(User.created_by_agent_id == agent_caller.id)
    if user_id:
        online_count_q = online_count_q.where(DeviceBinding.user_id == user_id)
    global_online = (await main_db.execute(online_count_q)).scalar_one()

    return {
        "devices":      devices,
        "total":        total,
        "online_count": global_online,
        "page":         page,
        "page_size":    page_size,
    }


# ── T026 按游戏项目查询 ───────────────────────────────────────

@router.get("/{game_project_code}", summary="管理后台设备监控（T026）")
async def list_devices_admin(
    game_project_code: str,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数"),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    device_status: str | None = Query(
        default=None, alias="status",
        description="按设备状态过滤：running / idle / error / offline",
    ),
    online_only: bool = Query(default=False, description="只返回在线设备"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    管理后台设备监控（T026）。按指定游戏项目查询，带 Redis 实时状态。

    Admin Token → 全量；Agent Token → 权限范围内。
    """
    admin, agent = caller

    if admin is not None:
        return await get_admin_device_list(
            game_project_code=game_project_code,
            main_db=main_db,
            redis=redis,
            page=page,
            page_size=page_size,
            user_id_filter=user_id,
            status_filter=device_status,
            online_only=online_only,
        )
    else:
        return await get_agent_device_list(
            game_project_code=game_project_code,
            agent=agent,
            main_db=main_db,
            redis=redis,
            page=page,
            page_size=page_size,
            user_id_filter=user_id,
            status_filter=device_status,
            online_only=online_only,
        )
