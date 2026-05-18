r"""
文件位置: app/services/device_service.py
文件名称: device_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-18
版本: V1.4.0
功能说明:
    设备数据服务层，包含三个业务逻辑：
      - process_heartbeat()  安卓脚本心跳上报（写 Redis）
      - get_device_list()    PC 中控拉取设备列表（Redis + 游戏库回落）
      - get_device_data()    PC 中控拉取单台设备详情

    当前设备标识口径：
      1. device_id = 设备编号，同一账号、同一项目下唯一。
      2. connection_type / connection_label 仅属于 PCControl 本地显示，不进入后端设备链。

改进历史:
    V1.4.0 (2026-05-18) - 从后端设备链移除 connection_type / connection_label。
    V1.3.0 (2026-05-18) - 移除旧脱敏日志调用；维持新设备标识主链。
    V1.2.0 (2026-05-17) - 删除 IMSI 上传链；心跳与查询链路新增 device_id / connection_type / connection_label。
    V1.1.0 (2026-05-07) - 移除旧 IMSI 响应字段。
    V1.0.1 - 设备绑定校验改为用户 × 项目 × 设备维度
    V1.0.0 - 初始版本
"""

import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import (
    get_heartbeat,
    get_user_heartbeats,
    set_heartbeat,
)
from app.core.utils import get_game_project_by_code as _get_game_project
from app.database import _get_game_engine, _game_session_factories
from app.models.game.models import DeviceRuntime
from app.models.main.models import Authorization, DeviceBinding, User
from app.schemas.device import (
    DeviceDataResponse,
    DeviceListResponse,
    DeviceStatus,
    HeartbeatRequest,
    HeartbeatResponse,
)

logger = logging.getLogger(__name__)

_OFFLINE_THRESHOLD_SECONDS = 120


async def process_heartbeat(
    body: HeartbeatRequest,
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> HeartbeatResponse:
    game_project = await _get_game_project(main_db, game_project_code)
    await _assert_active_authorization(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
    )
    binding = await _get_active_binding(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
        device_id=body.device_id,
    )
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="设备未绑定到当前项目，拒绝上报",
        )

    now_ts = datetime.now(timezone.utc)
    binding.last_seen_at = now_ts
    if body.connection_type is not None:
        binding.connection_type = body.connection_type
    if body.connection_label is not None:
        binding.connection_label = body.connection_label
    payload = {
        "status": body.status,
        "last_seen": int(now_ts.timestamp()),
        "game_data": body.game_data,
        "user_id": current_user.id,
        "game_id": game_project.id,
        "device_id": binding.device_id,
        "connection_type": binding.connection_type,
        "connection_label": binding.connection_label,
    }
    await set_heartbeat(
        redis=redis,
        game_id=game_project.id,
        user_id=current_user.id,
        device_id=body.device_id,
        payload=payload,
    )
    return HeartbeatResponse()


async def get_device_list(
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> DeviceListResponse:
    game_project = await _get_game_project(main_db, game_project_code)
    await _assert_active_authorization(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
    )

    online_hbs = await get_user_heartbeats(redis, game_project.id, current_user.id)
    online_device_ids: set[str] = set()
    devices: list[DeviceStatus] = []

    for hb in online_hbs:
        data = hb["data"]
        last_seen_ts = data.get("last_seen", 0)
        devices.append(DeviceStatus(
            device_id=hb["device_id"],
            connection_type=data.get("connection_type"),
            connection_label=data.get("connection_label"),
            user_id=current_user.id,
            status=data.get("status"),
            last_seen=datetime.fromtimestamp(last_seen_ts, tz=timezone.utc) if last_seen_ts else None,
            game_data=data.get("game_data"),
            is_online=True,
        ))
        online_device_ids.add(hb["device_id"])

    offline_from_game_db = await _get_offline_devices_from_db(
        game_project_code=game_project_code,
        user_id=current_user.id,
        exclude_device_ids=online_device_ids,
    )
    for d in offline_from_game_db:
        online_device_ids.add(d.device_id)
    devices.extend(offline_from_game_db)

    main_bindings = await _get_devices_from_main_db(
        main_db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
        exclude_device_ids=online_device_ids,
    )
    devices.extend(main_bindings)

    return DeviceListResponse(
        devices=devices,
        total=len(devices),
        online_count=len(online_device_ids),
    )


async def get_device_data(
    device_id: str,
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> DeviceDataResponse:
    game_project = await _get_game_project(main_db, game_project_code)
    await _assert_active_authorization(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
    )
    binding = await _get_active_binding(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
        device_id=device_id,
    )
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="设备未绑定到当前项目，拒绝上报",
        )

    cached = await get_heartbeat(
        redis=redis,
        game_id=game_project.id,
        user_id=current_user.id,
        device_id=device_id,
    )
    if cached:
        last_seen_ts = cached.get("last_seen", 0)
        return DeviceDataResponse(
            device_id=device_id,
            connection_type=cached.get("connection_type"),
            connection_label=cached.get("connection_label"),
            user_id=current_user.id,
            status=cached.get("status"),
            last_seen=datetime.fromtimestamp(last_seen_ts, tz=timezone.utc) if last_seen_ts else None,
            game_data=cached.get("game_data"),
            is_online=True,
            source="redis",
        )

    db_record = await _get_device_runtime_from_db(
        game_project_code=game_project_code,
        user_id=current_user.id,
        device_id=device_id,
    )
    if db_record:
        return DeviceDataResponse(
            device_id=db_record.device_id,
            connection_type=db_record.connection_type,
            connection_label=db_record.connection_label,
            user_id=db_record.user_id,
            status=db_record.status,
            last_seen=db_record.last_seen,
            game_data=db_record.game_data,
            is_online=False,
            source="database",
        )

    return DeviceDataResponse(
        device_id=binding.device_id,
        connection_type=binding.connection_type,
        connection_label=binding.connection_label,
        user_id=current_user.id,
        status=None,
        last_seen=None,
        game_data=None,
        is_online=False,
        source="not_found",
    )


async def _assert_active_authorization(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
) -> None:
    result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user_id,
            Authorization.game_project_id == game_project_id,
            Authorization.status == "active",
        )
    )
    auth = result.scalar_one_or_none()
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="项目授权已停用或不存在，拒绝设备访问",
        )

    if auth.valid_until:
        valid_until = auth.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_until <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="项目授权已过期，拒绝设备访问",
            )


async def _get_active_binding(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
    device_id: str,
) -> DeviceBinding | None:
    result = await db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == user_id,
            DeviceBinding.game_project_id == game_project_id,
            DeviceBinding.device_id == device_id,
            DeviceBinding.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def _get_offline_devices_from_db(
    game_project_code: str,
    user_id: int,
    exclude_device_ids: set[str],
) -> list[DeviceStatus]:
    try:
        _get_game_engine(game_project_code)
        async with _game_session_factories[game_project_code]() as session:
            result = await session.execute(
                select(DeviceRuntime).where(
                    DeviceRuntime.user_id == user_id,
                )
            )
            records = result.scalars().all()

        offline = []
        for rec in records:
            if rec.device_id not in exclude_device_ids:
                offline.append(DeviceStatus(
                    device_id=rec.device_id,
                    connection_type=rec.connection_type,
                    connection_label=rec.connection_label,
                    user_id=rec.user_id,
                    status=rec.status or "offline",
                    last_seen=rec.last_seen,
                    game_data=rec.game_data,
                    is_online=False,
                ))
        return offline

    except Exception as exc:
        logger.warning("游戏库离线设备查询失败 (%s): %s", game_project_code, exc)
        return []


async def _get_device_runtime_from_db(
    game_project_code: str,
    user_id: int,
    device_id: str,
) -> DeviceRuntime | None:
    try:
        _get_game_engine(game_project_code)
        async with _game_session_factories[game_project_code]() as session:
            result = await session.execute(
                select(DeviceRuntime).where(
                    DeviceRuntime.user_id == user_id,
                    DeviceRuntime.device_id == device_id,
                )
            )
            return result.scalar_one_or_none()
    except Exception as exc:
        logger.warning(
            "游戏库设备运行时查询失败 (%s, uid=%s, device_id=%s): %s",
            game_project_code,
            user_id,
            device_id,
            exc,
        )
        return None


async def _get_devices_from_main_db(
    main_db: AsyncSession,
    user_id: int,
    game_project_id: int,
    exclude_device_ids: set[str],
) -> list[DeviceStatus]:
    result = await main_db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == user_id,
            DeviceBinding.game_project_id == game_project_id,
            DeviceBinding.status == "active",
        )
    )
    bindings = result.scalars().all()

    now = datetime.now(timezone.utc)
    offline_threshold = timedelta(seconds=_OFFLINE_THRESHOLD_SECONDS)
    devices = []
    for b in bindings:
        if b.device_id in exclude_device_ids:
            continue
        is_online = False
        if b.last_seen_at:
            lsa = b.last_seen_at
            if lsa.tzinfo is None:
                lsa = lsa.replace(tzinfo=timezone.utc)
            is_online = (now - lsa) <= offline_threshold
        if is_online:
            exclude_device_ids.add(b.device_id)

        devices.append(DeviceStatus(
            device_id=b.device_id,
            connection_type=b.connection_type,
            connection_label=b.connection_label,
            user_id=b.user_id,
            status="idle" if is_online else "offline",
            last_seen=b.last_seen_at,
            game_data=None,
            is_online=is_online,
        ))
    return devices
