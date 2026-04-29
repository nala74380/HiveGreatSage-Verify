r"""
文件位置: app/services/device_admin_service.py
名称: 管理后台设备监控服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
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

    在线状态判断策略（与 device_service.py 保持一致）：
      1. Redis SCAN device:runtime:{game_id}:* 获取全部在线设备 ID
      2. 查游戏库 device_runtime 表补充离线设备记录
      3. 合并后用主库 user 表关联用户名

关联文档:
    [[01-网络验证系统/待决策清单]] T026
    [[01-网络验证系统/架构设计]] 9. API 端点清单

改进历史:
    V1.0.0 - 初始版本（T026）
调试信息:
    已知问题: 游戏库未初始化时 Redis 数据仍正常返回（优雅降级）
"""

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_all_heartbeats_for_game
from app.database import _get_game_engine, _game_session_factories
from app.models.game.models import DeviceRuntime
from app.models.main.models import Agent, GameProject, User

logger = logging.getLogger(__name__)


# ── 响应数据结构（轻量，不引入额外 Pydantic 导入循环）────────
# 由 router 层直接构造 dict 后经 response_model 序列化

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
    """
    管理员查看指定游戏项目下所有设备（Admin Token 专用）。

    返回字典结构：
      {
        "devices": [...],
        "total": int,
        "online_count": int,
        "page": int,
        "page_size": int,
        "game_project_code": str,
      }
    """
    game_project = await _get_game_project_or_404(main_db, game_project_code)
    return await _build_device_list(
        game_project=game_project,
        main_db=main_db,
        redis=redis,
        allowed_user_ids=None,   # None = 不限制，查所有用户
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
    """
    代理查看自己权限范围内的设备（Agent Token 专用）。

    权限范围（D007）：代理本身 + 所有下级代理创建的用户的设备。
    """
    game_project = await _get_game_project_or_404(main_db, game_project_code)

    # 用 WITH RECURSIVE 获取代理权限范围内所有代理 ID
    scope_agent_ids = await _get_agent_scope_ids(agent.id, main_db)

    # 查这些代理创建的用户 ID
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


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_game_project_or_404(db: AsyncSession, code_name: str) -> GameProject:
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


async def _get_agent_scope_ids(agent_id: int, db: AsyncSession) -> list[int]:
    """WITH RECURSIVE 获取代理权限范围内所有代理 ID（含自身）。"""
    sql = text("""
        WITH RECURSIVE scope AS (
            SELECT id FROM agent WHERE id = :agent_id
            UNION ALL
            SELECT a.id FROM agent a
            INNER JOIN scope s ON a.parent_agent_id = s.id
        )
        SELECT id FROM scope
    """)
    result = await db.execute(sql, {"agent_id": agent_id})
    return [row[0] for row in result.all()]


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
    """
    构建设备列表（在线设备来自 Redis，离线设备来自游戏库）。

    allowed_user_ids=None 表示不限制（管理员视角）。
    """
    game_id = game_project.id
    game_code = game_project.code_name

    # Step 1: Redis 在线设备
    redis_heartbeats = await get_all_heartbeats_for_game(redis, game_id)
    online_map: dict[str, dict] = {}   # device_fp → heartbeat data
    for hb in redis_heartbeats:
        uid = hb["user_id"]
        if allowed_user_ids is not None and uid not in allowed_user_ids:
            continue
        if user_id_filter is not None and uid != user_id_filter:
            continue
        if status_filter and hb["data"].get("status") != status_filter:
            continue
        online_map[hb["device_fp"]] = hb["data"]

    # Step 2: 游戏库离线设备（仅在不过滤 online_only 时查询）
    offline_records: list[dict] = []
    if not online_only:
        offline_records = await _fetch_offline_from_db(
            game_code=game_code,
            exclude_device_ids=set(online_map.keys()),
            allowed_user_ids=allowed_user_ids,
            user_id_filter=user_id_filter,
            status_filter=status_filter,
        )

    # Step 3: 合并设备列表
    all_devices: list[dict] = []

    # 在线设备
    for device_fp, data in online_map.items():
        last_seen_ts = data.get("last_seen", 0)
        all_devices.append({
            "device_id": device_fp,
            "user_id": data.get("user_id"),
            "status": data.get("status"),
            "last_seen": datetime.fromtimestamp(last_seen_ts, tz=timezone.utc).isoformat()
                         if last_seen_ts else None,
            "game_data": data.get("game_data"),
            "is_online": True,
            "source": "redis",
        })

    # 离线设备
    for rec in offline_records:
        all_devices.append({
            "device_id": rec["device_id"],
            "user_id": rec["user_id"],
            "status": rec.get("status") or "offline",
            "last_seen": rec["last_seen"].isoformat() if rec["last_seen"] else None,
            "game_data": rec.get("game_data"),
            "is_online": False,
            "source": "database",
        })

    # Step 4: 批量关联用户名（一次查询，避免 N+1）
    all_user_ids = {d["user_id"] for d in all_devices if d["user_id"]}
    username_map: dict[int, str] = {}
    if all_user_ids:
        result = await main_db.execute(
            select(User.id, User.username).where(User.id.in_(all_user_ids))
        )
        username_map = {uid: uname for uid, uname in result.all()}

    for device in all_devices:
        device["username"] = username_map.get(device["user_id"], "unknown")

    # Step 5: 分页
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
    """从游戏库查询离线设备（不在 Redis 中的）。"""
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
                "device_id": r.device_id,
                "user_id": r.user_id,
                "status": r.status,
                "last_seen": r.last_seen,
                "game_data": r.game_data,
            }
            for r in records
            if r.device_id not in exclude_device_ids
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
