r"""
文件位置: app/routers/admin.py
文件名称: admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    管理后台路由：
      POST /admin/api/auth/login   — 管理员登录，获取 Admin Token
      GET  /admin/api/dashboard    — 平台统计概览

改进历史:
    V1.0.0 - 从存根重写，增加管理员登录和仪表盘统计
调试信息:
    已知问题: 无
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import and_, cast, func, select
from sqlalchemy import Date as SADate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin, Agent, DeviceBinding, GameProject, LoginLog, User
from app.schemas.agent import AdminLoginRequest, AdminLoginResponse
from app.services.agent_service import admin_login

router = APIRouter()


@router.post("/auth/login", response_model=AdminLoginResponse)
async def admin_login_endpoint(
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_main_db),
) -> AdminLoginResponse:
    """
    管理员登录，返回 Admin Token（有效期 8 小时）。
    此接口无需鉴权，是唯一公开的 /admin/api 接口。
    """
    return await admin_login(body=body, db=db)


@router.get("/dashboard")
async def admin_dashboard(
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """平台统计概览（总用户数、总代理数、活跃游戏项目数）。"""
    user_count = (await db.execute(
        select(func.count(User.id)).where(User.is_deleted == False)  # noqa: E712
    )).scalar_one()
    agent_count = (await db.execute(select(func.count(Agent.id)))).scalar_one()
    project_count = (await db.execute(
        select(func.count(GameProject.id)).where(GameProject.is_active == True)
    )).scalar_one()

    return {
        "admin": current_admin.username,
        "total_users": user_count,
        "total_agents": agent_count,
        "active_projects": project_count,
    }


@router.get("/login-logs/")
async def list_login_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    success: bool | None = Query(default=None),
    client_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    date_to:   str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """登录日志列表（管理员专用）。"""
    query = select(LoginLog, User).outerjoin(User, LoginLog.user_id == User.id)

    filters = []
    if success is not None:
        filters.append(LoginLog.success == success)
    if client_type:
        filters.append(LoginLog.client_type == client_type)
    if date_from:
        filters.append(cast(LoginLog.login_at, SADate) >= date_from)
    if date_to:
        filters.append(cast(LoginLog.login_at, SADate) <= date_to)
    if filters:
        query = query.where(and_(*filters))

    total = (await db.execute(
        select(func.count()).select_from(
            select(LoginLog).where(and_(*filters) if filters else True).subquery()
        )
    )).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(LoginLog.login_at.desc()).offset(offset).limit(page_size)
    )
    rows = result.all()

    logs = [
        {
            "id":                 log.id,
            "user_id":            log.user_id,
            "username":           user.username if user else None,
            "device_fingerprint": log.device_fingerprint,
            "ip_address":         str(log.ip_address) if log.ip_address else None,
            "client_type":        log.client_type,
            "game_project_id":    log.game_project_id,
            "success":            log.success,
            "fail_reason":        log.fail_reason,
            "login_at":           log.login_at.isoformat() if log.login_at else None,
        }
        for log, user in rows
    ]

    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/debug/device-bindings/{user_id}")
async def debug_device_bindings(
    user_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """说诊端点：直接查 DeviceBinding 表原始数据（不过滤 status）"""
    result = await db.execute(
        select(DeviceBinding).where(DeviceBinding.user_id == user_id)
    )
    bindings = result.scalars().all()
    return {
        "user_id":      user_id,
        "total":        len(bindings),
        "bindings": [
            {
                "id":                 b.id,
                "device_fingerprint": b.device_fingerprint,
                "status":             b.status,
                "last_seen_at":       b.last_seen_at.isoformat() if b.last_seen_at else None,
                "bound_at":           b.bound_at.isoformat() if b.bound_at else None,
            }
            for b in bindings
        ],
    }


@router.get("/users/{user_id}/devices")
async def get_user_devices(
    user_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """查询指定用户的设备绑定列表（管理员专用）。"""
    # 不过滤 status，返回所有记录（包括 unbound），方便调试
    result = await db.execute(
        select(DeviceBinding)
        .where(DeviceBinding.user_id == user_id)
        .order_by(DeviceBinding.bound_at.desc())
    )
    bindings = result.scalars().all()

    logger.info(f"[get_user_devices] user_id={user_id}, 共询到 {len(bindings)} 条 DeviceBinding")
    for b in bindings:
        logger.debug(f"  -> id={b.id} fp={b.device_fingerprint[:16]}... status={b.status!r} last_seen={b.last_seen_at}")

    now = datetime.now(timezone.utc)
    online_threshold = timedelta(seconds=90)

    return {
        "devices": [
            {
                "id":                 b.id,
                "device_fingerprint": b.device_fingerprint,
                "bound_at":           b.bound_at.isoformat() if b.bound_at else None,
                "last_seen_at":       b.last_seen_at.isoformat() if b.last_seen_at else None,
                "status":             b.status,
                "is_online": (
                    b.last_seen_at is not None
                    and (now - (
                        b.last_seen_at if b.last_seen_at.tzinfo
                        else b.last_seen_at.replace(tzinfo=timezone.utc)
                    )) <= online_threshold
                ),
            }
            for b in bindings
        ]
    }


@router.delete("/users/{user_id}/devices/{binding_id}", status_code=204)
async def unbind_device(
    user_id: int,
    binding_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """解绑设备（软删除）。"""
    result = await db.execute(
        select(DeviceBinding).where(
            DeviceBinding.id == binding_id,
            DeviceBinding.user_id == user_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备绑定记录不存在")
    binding.status = "unbound"
    await db.commit()


# ── 删除接口 ────────────────────────────────────────────

@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """软删除用户（is_deleted=True，默认列表不再显示）。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.is_deleted = True
    await db.commit()


@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """软删除代理（状态改为 suspended）。"""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在")
    agent.status = "suspended"
    await db.commit()


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """软删除项目（is_active 改为 False）。"""
    result = await db.execute(select(GameProject).where(GameProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    project.is_active = False
    await db.commit()
