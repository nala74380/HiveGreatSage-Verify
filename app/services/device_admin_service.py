r"""
文件位置: app/services/device_admin_service.py
名称: 管理后台设备监控服务层
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-18
版本: V1.3.0
功能说明:
    T026 — 管理后台设备监控，支持 Admin / Agent 两种权限视角。

    Admin Token 视角：
      - 可查看指定游戏项目下所有用户的全部设备
      - 支持按 user_id / status / is_online 过滤
      - 分页返回

    Agent Token 视角：
      - 只能查看自己权限范围内（自己 + 所有下级代理）的用户的设备
      - 过滤方式：先用 WITH RECURSIVE 取出所有子代理 ID，
        再查这些代理创建的用户，再查对应设备
      - 支持同样的过滤参数

    当前设备标识口径：
      - device_fingerprint = 内部稳定绑定键
      - device_id = 用户自定义设备编号
      - connection_type / connection_label = 连接标识

改进历史:
    V1.3.0 - 删除旧脱敏 / 摘要字段口径，统一返回设备原文字段。
    V1.2.0 - 项目维度设备列表移除 device_id 原文输出
    V1.1.0 - 项目维度设备列表补充 device_id / device_fingerprint / connection 标识字段
    V1.0.0 - 初始版本（T026）
"""

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_all_heartbeats_for_game
from app.core.utils import get_agent_scope_ids as _get_agent_scope_ids, get_game_project_by_code as _get_game_project_or_404
from app.database import _get_game_engine, _game_session_factories
from app.models.game.models import DeviceRuntime
from app.models.main.models import Agent, GameProject, User

logger = logging.getLogger(__name__)


async def get_admin_device_list(
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
    page: int = 1,
    page_size: int = 50,
    user_id_filter: int | None = None,
    status_filter: str | None = None,
    online_only: bool = False,
) -> dict:
    game_project = await _get_game_project_or_404(main_db, game_project_code)
    return await _build_device_list(
        game_project=game_project,
        main_db=main_db,
        redis=redis,
        allowed_user_ids=None,
        user_id_filter=user_id_filter,
        status_filter=status_filter,
        online_only=online_only,
        page=page,
        page_size=page_size,
    )


async def get_agent_device_list(
    game_project_code: str,
    agent: Agent,
    main_db: AsyncSession,
    redis: aioredis.Redis,
    page: int = 1,
    page_size: int = 50,
    user_id_filter: int | None = None,
    status_filter: str | None = None,
    online_only: bool = False,
) -> dict:
    game_project = await _get_game_project_or_404(main_db, game_project_code)

    scope_agent_ids = await _get_agent_scope_ids(main_db, agent.id)

    result = await main_db.execute(
        select(User.id).where(
            User.created_by_agent_id.in_(scope_agent_ids),
            User.status == "active",
        )
    )
    allowed_user_ids = set(result.scalars().all())

    if not allowed_user_ids:
        return _empty_device_list(game_project_code, page, page_size)

    return await _build_device_list(
        game_project=game_project,
        main_db=main_db,
        redis=redis,
        allowed_user_ids=allowed_user_ids,
        user_id_filter=user_id_filter,
        status_filter=status_filter,
        online_only=online_only,
        page=page,
        page_size=page_size,
    )


def _device_identity_fields(device_fingerprint: str, device_id: str | None = None) -> dict:
    return {
        "device_id": device_id,
        "device_fingerprint": device_fingerprint,
    }


async def _build_device_list(
    game_project: GameProject,
    main_db: AsyncSession,
    redis: aioredis.Redis,
    allowed_user_ids: set[int] | None,
    user_id_filter: int | None,
    status_filter: str | None,
    online_only: bool,
    page: int,
    page_size: int,
) -> dict:
    game_id = game_project.id
    game_code = game_project.code_name

    redis_heartbeats = await get_all_heartbeats_for_game(redis, game_id)
    online_map: dict[str, dict] = {}
    for hb in redis_heartbeats:
        uid = hb["user_id"]
        if allowed_user_ids is not None and uid not in allowed_user_ids:
            continue
        if user_id_filter is not None and uid != user_id_filter:
            continue
        if status_filter and hb["data"].get("status") != status_filter:
            continue
        online_map[hb["device_fp"]] = hb["data"]

    offline_records: list[dict] = []
    if not online_only:
        offline_records = await _fetch_offline_from_db(
            game_code=game_code,
            exclude_device_ids=set(online_map.keys()),
            allowed_user_ids=allowed_user_ids,
            user_id_filter=user_id_filter,
            status_filter=status_filter,
        )

    all_devices: list[dict] = []

    for device_fp, data in online_map.items():
        last_seen_ts = data.get("last_seen", 0)
        all_devices.append({
            **_device_identity_fields(device_fp, data.get("device_id")),
            "connection_type": data.get("connection_type"),
            "connection_label": data.get("connection_label"),
            "user_id": data.get("user_id"),
            "status": data.get("status"),
            "last_seen": datetime.fromtimestamp(last_seen_ts, tz=timezone.utc).isoformat()
                         if last_seen_ts else None,
            "game_data": data.get("game_data"),
            "is_online": True,
            "source": "redis",
        })

    for rec in offline_records:
        device_fingerprint = rec["device_fingerprint"]
        all_devices.append({
            **_device_identity_fields(device_fingerprint, rec.get("device_id")),
            "connection_type": rec.get("connection_type"),
            "connection_label": rec.get("connection_label"),
            "user_id": rec["user_id"],
            "status": rec.get("status") or "offline",
            "last_seen": rec["last_seen"].isoformat() if rec["last_seen"] else None,
            "game_data": rec.get("game_data"),
            "is_online": False,
            "source": "database",
        })

    all_user_ids = {d["user_id"] for d in all_devices if d["user_id"]}
    username_map: dict[int, str] = {}
    if all_user_ids:
        result = await main_db.execute(
            select(User.id, User.username).where(User.id.in_(all_user_ids))
        )
        username_map = {uid: uname for uid, uname in result.all()}

    for device in all_devices:
        device["username"] = username_map.get(device["user_id"], "unknown")

    total = len(all_devices)
    online_count = sum(1 for d in all_devices if d["is_online"])
    offset = (page - 1) * page_size
    page_devices = all_devices[offset: offset + page_size]

    return {
        "devices": page_devices,
        "total": total,
        "online_count": online_count,
        "page": page,
        "page_size": page_size,
        "game_project_code": game_project.code_name,
    }


async def _fetch_offline_from_db(
    game_code: str,
    exclude_device_ids: set[str],
    allowed_user_ids: set[int] | None,
    user_id_filter: int | None,
    status_filter: str | None,
) -> list[dict]:
    try:
        _get_game_engine(game_code)
        async with _game_session_factories[game_code]() as session:
            query = select(DeviceRuntime)

            if allowed_user_ids is not None:
                query = query.where(DeviceRuntime.user_id.in_(allowed_user_ids))
            if user_id_filter is not None:
                query = query.where(DeviceRuntime.user_id == user_id_filter)
            if status_filter:
                query = query.where(DeviceRuntime.status == status_filter)

            result = await session.execute(query)
            records = result.scalars().all()

        return [
            {
                "device_fingerprint": r.device_fingerprint,
                "device_id": r.device_id,
                "connection_type": r.connection_type,
                "connection_label": r.connection_label,
                "user_id": r.user_id,
                "status": r.status,
                "last_seen": r.last_seen,
                "game_data": r.game_data,
            }
            for r in records
            if r.device_fingerprint not in exclude_device_ids
        ]
    except Exception as e:
        logger.warning("游戏库离线设备查询失败（优雅降级）: %s", e)
        return []


def _empty_device_list(game_project_code: str, page: int, page_size: int) -> dict:
    return {
        "devices": [],
        "total": 0,
        "online_count": 0,
        "page": page,
        "page_size": page_size,
        "game_project_code": game_project_code,
    }
