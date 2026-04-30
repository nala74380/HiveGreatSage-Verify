r"""
文件位置: app/routers/device_admin.py
名称: 管理后台设备监控路由
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-04-30
版本: V2.2.0
功能说明:
    管理后台设备监控路由。

    全局设备监控:
      GET /admin/api/devices/

    项目维度设备监控:
      GET /admin/api/devices/{game_project_code}

设计边界:
    1. /admin/api/devices/* 是 Admin / Agent 后台设备监控接口。
    2. /api/device/* 是 PC 中控 / 安卓脚本 User Token 终端接口。
    3. 后台设备监控不应调用 User Token 专用接口。
    4. 在线状态采用 Redis + DeviceBinding.last_seen_at 双源判断。
    5. Admin 可查看全平台设备。
    6. Agent 可查看自己及下级代理创建用户的设备。

改进历史:
    V2.2.0 (2026-04-30)
      - 全局设备列表补齐项目字段、用户字段、IMSI、绑定时间、来源字段。
      - 全局设备列表支持 user_id / keyword / project_id / project_code / status / online_only 过滤。
      - Agent 视角从“直属用户”升级为“自己 + 下级代理用户”。
      - 返回 running_count，便于前端统计。
    V2.1.0 (2026-04-28)
      - T021 双源在线判断（Redis+DB），心跳同步更新 last_seen_at。
    V2.0.0 (2026-04-26)
      - T021 全局总览正式实现。
    V1.0.1 (2026-04-26)
      - T021 占位返回 501。
    V1.0.0 (2026-04-25)
      - T026 初始实现。
"""

import json
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.core.security import decode_admin_token, decode_agent_token
from app.database import get_main_db
from app.models.main.models import Admin, Agent, DeviceBinding, GameProject, User
from app.services.device_admin_service import (
    get_admin_device_list,
    get_agent_device_list,
)

router = APIRouter()
_http_bearer = HTTPBearer()

# 在线判定阈值：与 device_service._OFFLINE_THRESHOLD_SECONDS 保持一致。
_ONLINE_THRESHOLD = timedelta(seconds=90)


async def _get_admin_or_agent(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> tuple[Admin | None, Agent | None]:
    """解析 Admin 或 Agent Token。两者恰好有一个不为 None，否则返回 401。"""
    token = credentials.credentials

    try:
        payload = decode_admin_token(token)
        admin_id = int(payload["sub"])

        result = await db.execute(
            select(Admin).where(
                Admin.id == admin_id,
                Admin.status == "active",
            )
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
            select(Agent).where(
                Agent.id == agent_id,
                Agent.status == "active",
            )
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


async def _get_agent_scope_ids(agent_id: int, db: AsyncSession) -> list[int]:
    """
    获取代理权限范围内所有代理 ID。

    范围:
        当前代理自身 + 所有下级代理。
    """
    sql = text(
        """
        WITH RECURSIVE scope AS (
            SELECT id FROM agent WHERE id = :agent_id
            UNION ALL
            SELECT a.id
            FROM agent a
            INNER JOIN scope s ON a.parent_agent_id = s.id
        )
        SELECT id FROM scope
        """
    )

    result = await db.execute(sql, {"agent_id": agent_id})
    return [row[0] for row in result.all()]


def _normalize_datetime(value: datetime | None) -> datetime | None:
    """确保 datetime 带 timezone。"""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


async def _read_runtime_from_redis(
    *,
    redis: aioredis.Redis,
    game_project_id: int,
    user_id: int,
    device_fingerprint: str,
) -> dict | None:
    """
    读取设备实时运行数据。

    Key 格式:
        device:runtime:{game_id}:{user_id}:{device_fp}
    """
    redis_key = f"device:runtime:{game_project_id}:{user_id}:{device_fingerprint}"
    raw = await redis.get(redis_key)

    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None

    # 兼容旧数据或项目未知情况下的通配扫描。
    redis_pattern = f"device:runtime:*:{user_id}:{device_fingerprint}"
    async for rkey in redis.scan_iter(redis_pattern):
        raw = await redis.get(rkey)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        break

    return None


@router.get("/", summary="全平台设备总览（Admin / Agent 后台）")
async def list_all_devices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    keyword: str | None = Query(default=None, description="按用户名 / 设备指纹模糊搜索"),
    project_id: int | None = Query(default=None, description="按项目 ID 过滤"),
    project_code: str | None = Query(default=None, description="按项目 code_name 过滤"),
    device_status: str | None = Query(
        default=None,
        alias="status",
        description="按运行状态过滤：running / idle / error / offline",
    ),
    online_only: bool = Query(default=False, description="只返回在线设备"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    全平台设备总览。

    在线判断双源策略:
      1. Redis 存在 device:runtime:{game_id}:{user_id}:{fp} → 在线。
      2. DeviceBinding.last_seen_at 在 90 秒内 → 在线。

    Admin Token:
      全平台所有用户。

    Agent Token:
      当前代理 + 下级代理创建的用户。
    """
    admin_caller, agent_caller = caller

    base_q = (
        select(DeviceBinding, User, GameProject)
        .join(User, DeviceBinding.user_id == User.id)
        .join(GameProject, DeviceBinding.game_project_id == GameProject.id)
        .where(
            DeviceBinding.status == "active",
            GameProject.is_active == True,  # noqa: E712
        )
    )

    if agent_caller is not None:
        scope_agent_ids = await _get_agent_scope_ids(agent_caller.id, main_db)

        if not scope_agent_ids:
            return {
                "devices": [],
                "total": 0,
                "online_count": 0,
                "offline_count": 0,
                "running_count": 0,
                "page": page,
                "page_size": page_size,
            }

        base_q = base_q.where(User.created_by_agent_id.in_(scope_agent_ids))

    if user_id:
        base_q = base_q.where(DeviceBinding.user_id == user_id)

    if project_id:
        base_q = base_q.where(DeviceBinding.game_project_id == project_id)

    if project_code:
        base_q = base_q.where(GameProject.code_name == project_code)

    if keyword:
        kw = f"%{keyword.strip()}%"
        base_q = base_q.where(
            (User.username.ilike(kw))
            | (DeviceBinding.device_fingerprint.ilike(kw))
            | (DeviceBinding.imsi.ilike(kw))
        )

    rows_result = await main_db.execute(
        base_q.order_by(DeviceBinding.last_seen_at.desc().nullslast(), DeviceBinding.id.desc())
    )
    rows = rows_result.all()

    now = datetime.now(timezone.utc)
    all_devices: list[dict] = []

    for binding, user, project in rows:
        redis_data = await _read_runtime_from_redis(
            redis=redis,
            game_project_id=project.id,
            user_id=binding.user_id,
            device_fingerprint=binding.device_fingerprint,
        )

        is_online_redis = redis_data is not None

        last_seen_db = _normalize_datetime(binding.last_seen_at)
        is_online_db = False

        if last_seen_db:
            is_online_db = (now - last_seen_db) <= _ONLINE_THRESHOLD

        is_online = is_online_redis or is_online_db

        if online_only and not is_online:
            continue

        game_data = None
        if redis_data:
            game_data = redis_data.get("game_data")

        if redis_data and redis_data.get("status"):
            status_val = redis_data["status"]
        elif is_online:
            status_val = "idle"
        else:
            status_val = "offline"

        if device_status and status_val != device_status:
            continue

        if redis_data and redis_data.get("last_seen"):
            try:
                last_seen = datetime.fromtimestamp(
                    int(redis_data["last_seen"]),
                    tz=timezone.utc,
                )
            except Exception:
                last_seen = last_seen_db
        else:
            last_seen = last_seen_db

        all_devices.append(
            {
                "binding_id": binding.id,
                "device_id": binding.device_fingerprint,
                "device_fingerprint": binding.device_fingerprint,

                "user_id": binding.user_id,
                "username": user.username,
                "user_status": user.status,
                "user_level": user.user_level,

                "project_id": project.id,
                "project_code": project.code_name,
                "project_name": project.display_name,
                "project_type": project.project_type,

                "status": status_val,
                "last_seen": last_seen.isoformat() if last_seen else None,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "bound_at": binding.bound_at.isoformat() if binding.bound_at else None,

                "imsi": binding.imsi,
                "game_data": game_data,

                "is_online": is_online,
                "source": "redis" if is_online_redis else "database",
            }
        )

    total = len(all_devices)
    online_count = sum(1 for item in all_devices if item["is_online"])
    running_count = sum(1 for item in all_devices if item["status"] == "running")

    offset = (page - 1) * page_size
    page_devices = all_devices[offset: offset + page_size]

    return {
        "devices": page_devices,
        "total": total,
        "online_count": online_count,
        "offline_count": total - online_count,
        "running_count": running_count,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{game_project_code}", summary="按项目查看设备监控")
async def list_devices_admin(
    game_project_code: str,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数"),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    device_status: str | None = Query(
        default=None,
        alias="status",
        description="按设备状态过滤：running / idle / error / offline",
    ),
    online_only: bool = Query(default=False, description="只返回在线设备"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    按指定游戏项目查询设备，带 Redis 实时状态。

    Admin Token:
      全量。

    Agent Token:
      权限范围内。
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