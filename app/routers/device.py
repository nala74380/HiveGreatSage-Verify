r"""
文件位置: app/routers/device.py
文件名称: device.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-17
版本: V1.1.0
功能说明:
    设备数据路由（薄层）：
      POST /api/device/heartbeat  — 安卓脚本心跳上报（按 user + project + device 限流）
      GET  /api/device/list       — PC 中控拉取当前用户所有设备状态
      GET  /api/device/data       — PC 中控拉取单台设备运行数据详情

    当前设备标识口径：
      1. device_id = 设备编号，同一账号、同一项目下唯一。

改进历史:
    V1.2.0 (2026-05-18) - 从后端设备链移除 connection_type / connection_label。
    V1.0.1 - IMSI 上传透传 game_project_code，按当前项目绑定记录写入
    V1.0.0 - 从存根重写为完整实现
调试信息:
    已知问题: 无
    403 Forbidden: 设备未绑定到当前账号
    429 Too Many Requests: 心跳频率超限（D5 限流）
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_game_project_code
from app.core.redis_client import get_redis, incr_rate_limit
from app.database import get_main_db
from app.models.main.models import User
from app.schemas.device import (
    DeviceDataResponse,
    DeviceListResponse,
    HeartbeatRequest,
    HeartbeatResponse,
)
from app.services.device_service import (
    get_device_data,
    get_device_list,
    process_heartbeat,
)

router = APIRouter()

_HEARTBEAT_RATE_LIMIT = 4
_HEARTBEAT_RATE_WINDOW = 60


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    body: HeartbeatRequest,
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> HeartbeatResponse:
    """安卓脚本心跳上报接口。"""
    heartbeat_identifier = f"{current_user.id}:{game_project_code}:{body.device_id}"
    allowed, count = await incr_rate_limit(
        redis,
        endpoint_tag="heartbeat",
        identifier=heartbeat_identifier,
        limit=_HEARTBEAT_RATE_LIMIT,
        window_seconds=_HEARTBEAT_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"心跳上报过于频繁（{count}/{_HEARTBEAT_RATE_LIMIT} 次/分钟）",
        )

    return await process_heartbeat(
        body=body,
        current_user=current_user,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )


@router.get("/list", response_model=DeviceListResponse)
async def list_devices(
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DeviceListResponse:
    """PC 中控拉取当前用户在当前游戏下的所有设备状态。"""
    return await get_device_list(
        current_user=current_user,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )


@router.get("/data", response_model=DeviceDataResponse)
async def device_data(
    device_id: str = Query(
        ...,
        description="要查询的设备编号",
        examples=["A118"],
    ),
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DeviceDataResponse:
    """PC 中控拉取单台设备的运行数据详情。"""
    return await get_device_data(
        device_id=device_id,
        current_user=current_user,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )
