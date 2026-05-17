r"""
文件位置: app/routers/admin.py
文件名称: admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-07
版本: V1.4.0
功能说明:
    管理后台路由：
      POST /admin/api/auth/login   — 管理员登录，获取 Admin Token
      GET  /admin/api/dashboard    — 平台统计概览

改进历史:
    V2.0.0 (2026-05-18): 登录日志当前直接返回 device_fingerprint 原文字段。
    V1.3.0 (2026-05-07): 用户设备列表与解绑审计中的设备指纹脱敏。
    V1.2.0 (2026-05-07): 管理员手动解绑设备接入 audit_log。
    V1.1.0 (2026-05-07): Admin 登录成功 / 失败接入 audit_log。
    V1.0.0 - 从存根重写，增加管理员登录和仪表盘统计
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from sqlalchemy import and_, cast, func, select
from sqlalchemy import Date as SADate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.redis_client import get_redis
from app.database import get_main_db
from app.models.main.accounting import AccountingLedgerEntry, AccountingWallet
from app.models.main.models import Admin, Agent, Authorization, DeviceBinding, GameProject, LoginLog, User
from app.schemas.agent import AdminLoginRequest, AdminLoginResponse
from app.services.agent_service import admin_login
from app.services.audit_service import create_audit_log
from app.services.stats_service import get_admin_dashboard_summary

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _device_fingerprint_fields(value: str | None) -> dict:
    return {
        "device_id": value,
    }


def _login_log_device_fields(log: LoginLog) -> dict:
    return {
        "device_fingerprint": log.device_fingerprint,
    }


@router.post("/auth/login", response_model=AdminLoginResponse)
async def admin_login_endpoint(
    body: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
) -> AdminLoginResponse:
    """
    管理员登录，返回 Admin Token（有效期 8 小时）。
    此接口无需鉴权，是唯一公开的 /admin/api 接口。
    """
    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    try:
        result = await admin_login(body=body, db=db)
    except HTTPException as exc:
        await create_audit_log(
            db=db,
            actor_type="admin",
            actor_id=None,
            action="auth.admin.login_failed",
            target_type="admin",
            target_id=body.username,
            summary=f"管理员 {body.username} 登录失败",
            metadata={
                "username": body.username,
                "success": False,
                "status_code": exc.status_code,
                "reason": str(exc.detail),
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        raise

    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=result.admin_id,
        action="auth.admin.login_success",
        target_type="admin",
        target_id=result.admin_id,
        summary=f"管理员 {result.username} 登录成功",
        metadata={
            "admin_id": result.admin_id,
            "username": result.username,
            "success": True,
            "expires_in": result.expires_in,
        },
        ip_address=client_ip,
        user_agent=user_agent,
    )
    return result


@router.get("/dashboard")
async def admin_dashboard(
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
    redis = Depends(get_redis),
) -> dict:
    """平台统计概览 — 单次请求返回全部仪表盘数据。"""
    return await get_admin_dashboard_summary(
        current_admin=current_admin,
        db=db,
        redis=redis,
    )


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
            **_login_log_device_fields(log),
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
    """诊断端点：直接查 DeviceBinding 表原始数据。"""
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
                **_device_fingerprint_fields(b.device_fingerprint),
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
    result = await db.execute(
        select(DeviceBinding)
        .where(DeviceBinding.user_id == user_id)
        .order_by(DeviceBinding.bound_at.desc())
    )
    bindings = result.scalars().all()

    logger.info(f"[get_user_devices] user_id={user_id}, 查询到 {len(bindings)} 条 DeviceBinding")
    for b in bindings:
        logger.debug(f"  -> id={b.id} fp={b.device_fingerprint} status={b.status!r} last_seen={b.last_seen_at}")

    now = datetime.now(timezone.utc)
    online_threshold = timedelta(seconds=90)

    return {
        "devices": [
            {
                "id":                 b.id,
                **_device_fingerprint_fields(b.device_fingerprint),
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
    request: Request,
    current_admin: Admin = Depends(get_current_admin),
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

    old_status = binding.status
    binding.status = "unbound"

    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="device_binding.admin_unbind",
        target_type="device_binding",
        target_id=binding.id,
        summary=f"管理员解绑用户 {user_id} 设备 {binding.id}",
        metadata={
            "binding_id": binding.id,
            "user_id": user_id,
            "game_project_id": binding.game_project_id,
            "device_fingerprint": binding.device_fingerprint,
            "old_status": old_status,
            "new_status": binding.status,
            "last_seen_at": binding.last_seen_at.isoformat() if binding.last_seen_at else None,
            "bound_at": binding.bound_at.isoformat() if binding.bound_at else None,
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
