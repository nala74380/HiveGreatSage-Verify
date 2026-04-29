r"""
文件位置: app/routers/device.py
文件名称: device.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    设备数据路由（薄层）：
      POST /api/device/heartbeat  — 安卓脚本心跳上报（D5 限流：同 Token ≤4次/分钟）
      GET  /api/device/list       — PC 中控拉取当前用户所有设备状态
      GET  /api/device/data       — PC 中控拉取单台设备运行数据详情

    路由层职责：
      1. 鉴权（get_current_user + get_game_project_code）
      2. D5 限流（心跳接口）
      3. 调用 DeviceService，返回 HTTP 响应
      不包含任何业务判断逻辑。

关联文档:
    [[01-网络验证系统/架构设计]] 9. API 端点清单
    [[01-网络验证系统/Redis心跳落库策略]]

改进历史:
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
    ImsiUploadRequest,
    ImsiUploadResponse,
)
from app.services.device_service import (
    get_device_data,
    get_device_list,
    process_heartbeat,
    upload_imsi,
)

router = APIRouter()

# D5 决策：心跳接口同 Token 每分钟 ≤ 4 次
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
    """
    安卓脚本心跳上报接口。
    写入 Redis 缓冲层后立即返回，不等待落库（Celery 异步处理）。
    D5 限流：同 user_id 每分钟 ≤ 4 次（对应 30 秒上报间隔）。
    """
    # D5 限流：按 user_id 计数，防止异常频率上报
    allowed, count = await incr_rate_limit(
        redis,
        endpoint_tag="heartbeat",
        identifier=str(current_user.id),
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
    """
    PC 中控拉取当前用户在当前游戏下的所有设备状态。
    在线设备来自 Redis（实时），离线设备来自游戏库（历史落库数据）。
    建议 PC 中控每 10 秒轮询一次（D2 决策）。
    """
    return await get_device_list(
        current_user=current_user,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )


@router.post("/imsi", response_model=ImsiUploadResponse, summary="上传设备 IMSI")
async def upload_device_imsi(
    body: ImsiUploadRequest,
    current_user: User = Depends(get_current_user),
    main_db: AsyncSession = Depends(get_main_db),
) -> ImsiUploadResponse:
    """
    登录成功后上传设备 IMSI 码（T027，接入契约 §8）。

    IMSI 不参与登录验证，仅作为辅助标识存储。
    设备必须已绑定到当前账号（即登录时使用的设备）。
    """
    return await upload_imsi(
        body=body,
        current_user=current_user,
        db=main_db,
    )


@router.get("/data", response_model=DeviceDataResponse)
async def device_data(
    device_fingerprint: str = Query(
        ...,
        description="要查询的设备指纹",
        examples=["a1b2c3d4e5f6"],
    ),
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DeviceDataResponse:
    """
    PC 中控拉取单台设备的运行数据详情。
    优先读 Redis（实时），Redis 无数据时回落到游戏库。
    响应中 source 字段标明数据来源：redis / database / not_found。
    """
    return await get_device_data(
        device_fingerprint=device_fingerprint,
        current_user=current_user,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )
