r"""
文件位置: app/routers/device_admin.py
名称: 管理后台设备监控路由
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-07
版本: V2.3.0
功能说明:
    管理后台设备监控路由。

    普通全局设备列表:
      GET /admin/api/devices/
      - SQL 层先分页。
      - 只为当前页设备补 Redis 在线态。
      - 不默认全量 SCAN Redis，不默认全量拉取设备后 Python 分页。

    全局设备统计:
      GET /admin/api/devices/summary
      - 单独返回 total / online / offline / running 统计。
      - 允许执行 Redis 汇总扫描，但不混入普通分页列表。

    高成本全局设备搜索:
      GET /admin/api/devices/search
      - 用于 online_only / status 等依赖 Redis 在线态的筛选。
      - 显式限制 max_scan，避免误扫全量。

    项目维度设备监控:
      GET /admin/api/devices/{game_project_code}

设计边界:
    1. /admin/api/devices/* 是 Admin / Agent 后台设备监控接口。
    2. /api/device/* 是 PC 中控 / 安卓脚本 User Token 终端接口。
    3. 后台设备监控不应调用 User Token 专用接口。
    4. 普通列表接口不得默认全量扫描 Redis 后再分页。
    5. Admin 可查看全平台设备。
    6. Agent 可查看自己及下级代理创建用户的设备。

当前口径:
    - 项目编码对外统一使用 game_project_code。
    - 在线状态优先来自 Redis runtime key，DB last_seen_at 作为补充。
    - IMSI 当前仍按既有接口返回，后续需进入敏感字段脱敏治理。
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.core.security import decode_admin_token, decode_agent_token
from app.core.utils import get_agent_scope_ids as _get_agent_scope_ids
from app.database import get_main_db
from app.models.main.models import Admin, Agent, Authorization, DeviceBinding, GameProject, User
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


def _normalize_datetime(value: datetime | None) -> datetime | None:
    """确保 datetime 带 timezone。"""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def _decode_redis_key(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode("utf-8", errors="ignore")
    return str(key)


async def _read_runtime_from_redis(
    redis: aioredis.Redis,
    *,
    game_id: int,
    user_id: int,
    device_fingerprint: str,
) -> dict | None:
    """
    读取单台设备 Redis runtime。

    普通分页列表只对当前页设备执行 GET，避免默认全量 SCAN。
    """
    key = f"device:runtime:{game_id}:{user_id}:{device_fingerprint}"
    raw = await redis.get(key)
    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


async def _build_redis_online_map(
    redis: aioredis.Redis,
    *,
    pattern: str = "device:runtime:*",
    max_scan: int | None = None,
) -> dict[tuple[int, int, str], dict]:
    """
    显式高成本 Redis 汇总扫描。

    仅 summary / search 这类明确高成本接口允许调用。
    普通列表接口不得调用此函数。
    """
    online_map: dict[tuple[int, int, str], dict] = {}
    scanned = 0

    async for raw_key in redis.scan_iter(pattern):
        key = _decode_redis_key(raw_key)
        raw = await redis.get(raw_key)
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        # Key 格式：device:runtime:{game_id}:{user_id}:{device_fp}
        parts = key.split(":")
        if len(parts) >= 5:
            try:
                gid = int(parts[2])
                uid = int(parts[3])
                fp = parts[4]
                online_map[(gid, uid, fp)] = data
            except (ValueError, IndexError):
                pass

        scanned += 1
        if max_scan is not None and scanned >= max_scan:
            break

    return online_map


async def _build_base_query(
    *,
    db: AsyncSession,
    caller: tuple[Admin | None, Agent | None],
    user_id: int | None = None,
    keyword: str | None = None,
    project_id: int | None = None,
    project_code: str | None = None,
):
    """构建后台设备基础 SQL 查询。仅包含数据库可过滤条件。"""
    _admin_caller, agent_caller = caller

    base_q = (
        select(DeviceBinding, User, GameProject, Authorization)
        .join(User, DeviceBinding.user_id == User.id)
        .join(GameProject, DeviceBinding.game_project_id == GameProject.id)
        .outerjoin(
            Authorization,
            (Authorization.user_id == User.id)
            & (Authorization.game_project_id == GameProject.id)
            & (Authorization.status == "active"),
        )
        .where(
            DeviceBinding.status == "active",
            GameProject.is_active == True,  # noqa: E712
        )
    )

    if agent_caller is not None:
        scope_agent_ids = await _get_agent_scope_ids(db, agent_caller.id)
        if not scope_agent_ids:
            return None
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

    return base_q


def _runtime_status_and_last_seen(
    *,
    binding: DeviceBinding,
    redis_data: dict | None,
    now: datetime,
) -> tuple[bool, bool, str, datetime | None, dict | None]:
    """
    根据 Redis + DB 双源计算在线状态、运行状态、最后活跃时间和 game_data。

    Returns:
        is_online, is_online_redis, status_val, last_seen, game_data
    """
    is_online_redis = redis_data is not None

    last_seen_db = _normalize_datetime(binding.last_seen_at)
    is_online_db = bool(last_seen_db and (now - last_seen_db) <= _ONLINE_THRESHOLD)
    is_online = is_online_redis or is_online_db

    game_data = None
    if redis_data:
        game_data = redis_data.get("game_data")

    if redis_data and redis_data.get("status"):
        status_val = redis_data["status"]
    elif is_online:
        status_val = "idle"
    else:
        status_val = "offline"

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

    return is_online, is_online_redis, status_val, last_seen, game_data


def _device_response(
    *,
    binding: DeviceBinding,
    user: User,
    project: GameProject,
    authorization: Authorization | None,
    redis_data: dict | None,
    now: datetime,
) -> dict:
    is_online, is_online_redis, status_val, last_seen, game_data = _runtime_status_and_last_seen(
        binding=binding,
        redis_data=redis_data,
        now=now,
    )

    return {
        "binding_id": binding.id,
        "device_id": binding.device_fingerprint,
        "device_fingerprint": binding.device_fingerprint,
        "user_id": binding.user_id,
        "username": user.username,
        "user_status": user.status,
        "authorization_level": authorization.user_level if authorization else None,
        "project_id": project.id,
        "game_project_code": project.code_name,
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


@router.get("/", summary="全平台设备普通分页列表（Admin / Agent 后台）")
async def list_all_devices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    keyword: str | None = Query(default=None, description="按用户名 / 设备指纹 / IMSI 模糊搜索"),
    project_id: int | None = Query(default=None, description="按项目 ID 过滤"),
    project_code: str | None = Query(default=None, description="按项目 code_name 过滤"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    全平台设备普通分页列表。

    性能规则:
      - SQL 层先分页。
      - 只对当前页设备读取 Redis runtime。
      - 不返回全局 online_count / offline_count / running_count。
      - 全局统计请调用 /admin/api/devices/summary。
      - online_only / status 等 Redis 依赖筛选请调用 /admin/api/devices/search。
    """
    base_q = await _build_base_query(
        db=main_db,
        caller=caller,
        user_id=user_id,
        keyword=keyword,
        project_id=project_id,
        project_code=project_code,
    )

    if base_q is None:
        return {
            "devices": [],
            "total": 0,
            "page_online_count": 0,
            "page_offline_count": 0,
            "page_running_count": 0,
            "page": page,
            "page_size": page_size,
        }

    total = (
        await main_db.execute(select(func.count()).select_from(base_q.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    rows_result = await main_db.execute(
        base_q.order_by(DeviceBinding.last_seen_at.desc().nullslast(), DeviceBinding.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_result.all()

    now = datetime.now(timezone.utc)
    devices: list[dict] = []

    for binding, user, project, authorization in rows:
        redis_data = await _read_runtime_from_redis(
            redis,
            game_id=project.id,
            user_id=binding.user_id,
            device_fingerprint=binding.device_fingerprint,
        )
        devices.append(
            _device_response(
                binding=binding,
                user=user,
                project=project,
                authorization=authorization,
                redis_data=redis_data,
                now=now,
            )
        )

    page_online_count = sum(1 for item in devices if item["is_online"])
    page_running_count = sum(1 for item in devices if item["status"] == "running")

    return {
        "devices": devices,
        "total": int(total or 0),
        "page_online_count": page_online_count,
        "page_offline_count": len(devices) - page_online_count,
        "page_running_count": page_running_count,
        "page": page,
        "page_size": page_size,
    }


@router.get("/summary", summary="全平台设备统计摘要（Admin / Agent 后台）")
async def device_summary(
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    keyword: str | None = Query(default=None, description="按用户名 / 设备指纹 / IMSI 模糊搜索"),
    project_id: int | None = Query(default=None, description="按项目 ID 过滤"),
    project_code: str | None = Query(default=None, description="按项目 code_name 过滤"),
    max_scan: int = Query(default=20000, ge=100, le=100000, description="Redis 在线 key 最大扫描数量"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    全平台设备统计摘要。

    注意:
      - 这是显式统计接口，可执行 Redis 汇总扫描。
      - 普通列表不会调用本接口逻辑。
      - 大规模生产应进一步改为 Redis ZSET 在线索引或定时统计缓存。
    """
    base_q = await _build_base_query(
        db=main_db,
        caller=caller,
        user_id=user_id,
        keyword=keyword,
        project_id=project_id,
        project_code=project_code,
    )

    if base_q is None:
        return {
            "total": 0,
            "online_count": 0,
            "offline_count": 0,
            "running_count": 0,
            "redis_scanned_limit": max_scan,
        }

    rows_result = await main_db.execute(base_q)
    rows = rows_result.all()
    now = datetime.now(timezone.utc)
    redis_online_map = await _build_redis_online_map(redis, max_scan=max_scan)

    total = 0
    online_count = 0
    running_count = 0

    for binding, _user, project, _authorization in rows:
        redis_data = redis_online_map.get((project.id, binding.user_id, binding.device_fingerprint))
        is_online, _is_online_redis, status_val, _last_seen, _game_data = _runtime_status_and_last_seen(
            binding=binding,
            redis_data=redis_data,
            now=now,
        )
        total += 1
        if is_online:
            online_count += 1
        if status_val == "running":
            running_count += 1

    return {
        "total": total,
        "online_count": online_count,
        "offline_count": total - online_count,
        "running_count": running_count,
        "redis_scanned_limit": max_scan,
    }


@router.get("/search", summary="高成本全局设备搜索（Admin / Agent 后台）")
async def search_all_devices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None, description="按用户 ID 过滤"),
    keyword: str | None = Query(default=None, description="按用户名 / 设备指纹 / IMSI 模糊搜索"),
    project_id: int | None = Query(default=None, description="按项目 ID 过滤"),
    project_code: str | None = Query(default=None, description="按项目 code_name 过滤"),
    device_status: str | None = Query(
        default=None,
        alias="status",
        description="按运行状态过滤：running / idle / error / offline",
    ),
    online_only: bool = Query(default=False, description="只返回在线设备"),
    max_scan: int = Query(default=5000, ge=100, le=50000, description="最多从 SQL 候选集中扫描多少条设备"),
    caller: tuple = Depends(_get_admin_or_agent),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    高成本全局设备搜索。

    用途:
      - online_only=true
      - status=running / idle / error / offline

    限制:
      - 不保证返回全量精确 total，仅返回已扫描候选集内的 matched_total。
      - 大规模精确在线筛选应通过 Redis ZSET 在线索引重构。
    """
    base_q = await _build_base_query(
        db=main_db,
        caller=caller,
        user_id=user_id,
        keyword=keyword,
        project_id=project_id,
        project_code=project_code,
    )

    if base_q is None:
        return {
            "devices": [],
            "matched_total": 0,
            "scanned_total": 0,
            "page": page,
            "page_size": page_size,
            "max_scan": max_scan,
        }

    rows_result = await main_db.execute(
        base_q.order_by(DeviceBinding.last_seen_at.desc().nullslast(), DeviceBinding.id.desc())
        .limit(max_scan)
    )
    rows = rows_result.all()
    now = datetime.now(timezone.utc)
    matched: list[dict] = []

    for binding, user, project, authorization in rows:
        redis_data = await _read_runtime_from_redis(
            redis,
            game_id=project.id,
            user_id=binding.user_id,
            device_fingerprint=binding.device_fingerprint,
        )
        item = _device_response(
            binding=binding,
            user=user,
            project=project,
            authorization=authorization,
            redis_data=redis_data,
            now=now,
        )

        if online_only and not item["is_online"]:
            continue

        if device_status and item["status"] != device_status:
            continue

        matched.append(item)

    offset = (page - 1) * page_size
    page_devices = matched[offset: offset + page_size]

    return {
        "devices": page_devices,
        "matched_total": len(matched),
        "scanned_total": len(rows),
        "page_online_count": sum(1 for item in page_devices if item["is_online"]),
        "page_running_count": sum(1 for item in page_devices if item["status"] == "running"),
        "page": page,
        "page_size": page_size,
        "max_scan": max_scan,
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
