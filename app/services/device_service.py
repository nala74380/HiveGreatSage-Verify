r"""
文件位置: app/services/device_service.py
文件名称: device_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    设备数据服务层，包含三个业务逻辑：
      - process_heartbeat()  安卓脚本心跳上报（写 Redis）
      - get_device_list()    PC 中控拉取设备列表（Redis + 游戏库回落）
      - get_device_data()    PC 中控拉取单台设备详情

    设计要点：
      1. 心跳只写 Redis，不直接写 PostgreSQL；落库由 Celery 任务异步完成。
      2. device_list 优先读 Redis（实时），Redis 无数据则回落到游戏库（历史）。
      3. 游戏库会话通过 _get_game_engine / _game_session_factories 在服务层内部
         创建，不通过 FastAPI 依赖注入（因为 code_name 在运行时才能确定）。
      4. 所有跨库引用（user_id, device_id）在应用层校验，不依赖数据库外键。

    P1: 后续如需拆分数据访问层，再按实际重复度引入 repository 抽象。

关联文档:
    [[01-网络验证系统/Redis心跳落库策略]]
    [[01-网络验证系统/架构设计]] 第七节 Redis 使用策略

改进历史:
    V1.0.1 - 设备绑定校验改为用户 × 项目 × 设备维度
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
    游戏库会话使用内部工厂方法，确保已调用 _get_game_engine 初始化引擎。
"""

import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import (
    get_heartbeat,
    get_user_heartbeats,
    set_heartbeat,
)
from app.database import _get_game_engine, _game_session_factories
from app.models.game.models import DeviceRuntime
from app.models.main.models import DeviceBinding, GameProject, User
from app.schemas.device import (
    DeviceDataResponse,
    DeviceListResponse,
    DeviceStatus,
    HeartbeatRequest,
    HeartbeatResponse,
    ImsiUploadRequest,
    ImsiUploadResponse,
)

# 设备离线判定阈值：超过此时间未在 Redis 中出现则视为离线
_OFFLINE_THRESHOLD_SECONDS = 90


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def process_heartbeat(
    body: HeartbeatRequest,
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> HeartbeatResponse:
    """
    处理安卓脚本的心跳上报。

    执行步骤：
      1. 通过 code_name 查找游戏项目，取得 game_id
      2. 校验上报的设备已绑定到当前用户 + 当前项目（防止跨项目伪造上报）
      3. 将心跳数据写入 Redis（TTL=120s，超时自动判定为离线）
      4. 立即返回 200，不等待落库
    """
    game_project = await _get_game_project(main_db, game_project_code)
    await _assert_device_bound(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
        device_fingerprint=body.device_fingerprint,
    )

    # 同时更新当前项目 DeviceBinding.last_seen_at（让管理后台全局端点能用时间推断在线状态）
    now_ts = datetime.now(timezone.utc)
    result = await main_db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == current_user.id,
            DeviceBinding.game_project_id == game_project.id,
            DeviceBinding.device_fingerprint == body.device_fingerprint,
            DeviceBinding.status == "active",
        )
    )
    binding = result.scalar_one_or_none()
    if binding:
        binding.last_seen_at = now_ts

    payload = {
        "status": body.status,
        "last_seen": int(now_ts.timestamp()),
        "game_data": body.game_data,
        "user_id": current_user.id,
        "game_id": game_project.id,
    }
    await set_heartbeat(
        redis=redis,
        game_id=game_project.id,
        user_id=current_user.id,
        device_fp=body.device_fingerprint,
        payload=payload,
    )
    return HeartbeatResponse()


async def get_device_list(
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> DeviceListResponse:
    """
    拉取当前用户在当前游戏项目下的所有设备状态。

    数据源（三层兑退，D2 决策）：
      第 1 层：Redis 心跳（实时，安卓每 30s 上报）
      第 2 层：游戏库 device_runtime 表（历史落库数据）
      第 3 层：主库 DeviceBinding 表（登录时就建立，即使还没发心跳也能显示）
    """
    game_project = await _get_game_project(main_db, game_project_code)

    # 层 1：Redis 在线设备
    online_hbs = await get_user_heartbeats(redis, game_project.id, current_user.id)
    online_device_ids: set[str] = set()
    devices: list[DeviceStatus] = []

    for hb in online_hbs:
        data = hb["data"]
        last_seen_ts = data.get("last_seen", 0)
        devices.append(DeviceStatus(
            device_id=hb["device_fp"],
            user_id=current_user.id,
            status=data.get("status"),
            last_seen=datetime.fromtimestamp(last_seen_ts, tz=timezone.utc) if last_seen_ts else None,
            game_data=data.get("game_data"),
            is_online=True,
        ))
        online_device_ids.add(hb["device_fp"])

    # 层 2：游戏库离线设备
    offline_from_game_db = await _get_offline_devices_from_db(
        game_project_code=game_project_code,
        user_id=current_user.id,
        exclude_device_ids=online_device_ids,
    )
    for d in offline_from_game_db:
        online_device_ids.add(d.device_id)   # 避免主库层重复
    devices.extend(offline_from_game_db)

    # 层 3：主库 DeviceBinding（登录时就创建，无心跳也展示）
    # 只补充 Redis + 游戏库都没有的设备
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
    device_fingerprint: str,
    current_user: User,
    game_project_code: str,
    main_db: AsyncSession,
    redis: aioredis.Redis,
) -> DeviceDataResponse:
    """
    拉取单台设备的运行时数据详情。

    优先读 Redis（实时），Redis 无数据时回落到游戏库（最后一次落库数据）。
    若两处都没有数据，返回 source="not_found"。
    """
    game_project = await _get_game_project(main_db, game_project_code)
    await _assert_device_bound(
        db=main_db,
        user_id=current_user.id,
        game_project_id=game_project.id,
        device_fingerprint=device_fingerprint,
    )

    # 先查 Redis
    cached = await get_heartbeat(
        redis=redis,
        game_id=game_project.id,
        user_id=current_user.id,
        device_fp=device_fingerprint,
    )
    if cached:
        last_seen_ts = cached.get("last_seen", 0)
        return DeviceDataResponse(
            device_id=device_fingerprint,
            user_id=current_user.id,
            status=cached.get("status"),
            last_seen=datetime.fromtimestamp(last_seen_ts, tz=timezone.utc) if last_seen_ts else None,
            game_data=cached.get("game_data"),
            is_online=True,
            source="redis",
        )

    # Redis 无数据，回落游戏库
    db_record = await _get_device_runtime_from_db(
        game_project_code=game_project_code,
        user_id=current_user.id,
        device_fingerprint=device_fingerprint,
    )
    if db_record:
        return DeviceDataResponse(
            device_id=db_record.device_id,
            user_id=db_record.user_id,
            status=db_record.status,
            last_seen=db_record.last_seen,
            game_data=db_record.game_data,
            is_online=False,
            source="database",
        )

    return DeviceDataResponse(
        device_id=device_fingerprint,
        user_id=current_user.id,
        status=None,
        last_seen=None,
        game_data=None,
        is_online=False,
        source="not_found",
    )


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_game_project(db: AsyncSession, code_name: str) -> GameProject:
    """从主库查找游戏项目，不存在则抛 404。"""
    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == code_name,
            GameProject.is_active == True,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"游戏项目 '{code_name}' 不存在或已下线",
        )
    return project


async def _assert_device_bound(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
    device_fingerprint: str,
) -> None:
    """
    校验设备已绑定到当前用户和当前项目。
    防止用户伪造其他设备或跨项目上报心跳。
    """
    result = await db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == user_id,
            DeviceBinding.game_project_id == game_project_id,
            DeviceBinding.device_fingerprint == device_fingerprint,
            DeviceBinding.status == "active",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="设备未绑定到当前项目，拒绝上报",
        )


async def _get_offline_devices_from_db(
    game_project_code: str,
    user_id: int,
    exclude_device_ids: set[str],
) -> list[DeviceStatus]:
    """
    从游戏库中查询当前用户的离线设备记录（已在 Redis 中的在线设备排除在外）。
    """
    try:
        _get_game_engine(game_project_code)  # 确保引擎已创建
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
                    user_id=rec.user_id,
                    status=rec.status or "offline",
                    last_seen=rec.last_seen,
                    game_data=rec.game_data,
                    is_online=False,
                ))
        return offline

    except Exception:
        # 游戏库尚未初始化或连接失败时，优雅降级：只返回 Redis 的在线数据
        return []


async def _get_device_runtime_from_db(
    game_project_code: str,
    user_id: int,
    device_fingerprint: str,
) -> DeviceRuntime | None:
    """从游戏库查询当前用户单台设备的历史运行数据。"""
    try:
        _get_game_engine(game_project_code)
        async with _game_session_factories[game_project_code]() as session:
            result = await session.execute(
                select(DeviceRuntime).where(
                    DeviceRuntime.user_id == user_id,
                    DeviceRuntime.device_id == device_fingerprint,
                )
            )
            return result.scalar_one_or_none()
    except Exception:
        return None


async def _get_devices_from_main_db(
    main_db: AsyncSession,
    user_id: int,
    game_project_id: int,
    exclude_device_ids: set[str],
) -> list[DeviceStatus]:
    """
    第三层山山：从主库 DeviceBinding 表查询用户的设备绑定记录。

    登录时就会创建 DeviceBinding，所以即使还没有心跳，
    也能展示已绑定的设备列表（状态显示为离线）。
    """
    from datetime import timedelta
    from sqlalchemy import select

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
        if b.device_fingerprint in exclude_device_ids:
            continue
        # 用 last_seen_at 判断心跳是否在线
        is_online = False
        if b.last_seen_at:
            lsa = b.last_seen_at
            if lsa.tzinfo is None:
                lsa = lsa.replace(tzinfo=timezone.utc)
            is_online = (now - lsa) <= offline_threshold
        if is_online:
            exclude_device_ids.add(b.device_fingerprint)  # 勿重计在线数

        devices.append(DeviceStatus(
            device_id=b.device_fingerprint,
            user_id=b.user_id,
            status="idle" if is_online else "offline",
            last_seen=b.last_seen_at,
            game_data=None,
            is_online=is_online,
        ))
    return devices


async def upload_imsi(
    body: ImsiUploadRequest,
    current_user: User,
    game_project_code: str,
    db: AsyncSession,
) -> ImsiUploadResponse:
    """
    登录成功后上传设备 IMSI 码（T027，接入契约 §8）。

    设备必须已绑定到当前用户和当前项目，不允许为未绑定设备上传 IMSI。
    IMSI 不参与登录验证，仅作为辅助标识存储到 device_binding.imsi 字段。
    """
    game_project = await _get_game_project(db, game_project_code)
    result = await db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == current_user.id,
            DeviceBinding.game_project_id == game_project.id,
            DeviceBinding.device_fingerprint == body.device_fingerprint,
            DeviceBinding.status == "active",
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="设备未绑定到当前项目，无法上传 IMSI",
        )

    binding.imsi = body.imsi
    await db.flush()

    return ImsiUploadResponse(
        message="IMSI 上传成功",
        device_fingerprint=body.device_fingerprint,
        imsi=body.imsi,
    )
