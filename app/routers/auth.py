r"""
文件位置: app/routers/auth.py
文件名称: auth.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-07
版本: V1.2.0
功能说明:
    认证路由薄层：
      POST /api/auth/login      — 登录
      POST /api/auth/refresh    — 刷新 Access Token
      POST /api/auth/logout     — 登出
      POST /api/auth/revoke-all — 踢出所有 User Refresh Token 会话
      GET  /api/auth/me         — 获取当前用户在当前项目下的授权摘要

    当前字段口径:
      1. LoginResponse 返回 authorization_level / game_project_code。
      2. Access Token payload 使用 authorization_level / project_code。
      3. User.user_level 已不再作为授权等级来源。
      4. 登录成功 / 失败写入 audit_log，但不记录密码、Token 或密码哈希。

改进历史:
    V1.2.0 (2026-05-07) - User 登录成功 / 失败接入 audit_log。
    V1.1.0 (2026-05-02) - /me 改为 Authorization 授权摘要口径。
    V1.0.1 - 业务逻辑迁移至 services/auth_service.py。
    V1.0.0 - 初始版本。
"""

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.redis_client import get_redis, incr_rate_limit
from app.core.security import decode_access_token
from app.database import get_main_db
from app.models.main.models import GameProject, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MeResponse,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services.audit_service import create_audit_log
from app.services.auth_service import (
    _get_active_authorization,
    _is_authorization_expired,
    login_user,
    logout_user,
    refresh_access_token,
    revoke_all_devices,
)


router = APIRouter()
_http_bearer = HTTPBearer()

_LOGIN_RATE_LIMIT = 10
_LOGIN_RATE_WINDOW = 60


def _login_metadata(body: LoginRequest, *, client_ip: str, success: bool, reason: str | None = None) -> dict:
    """生成用户登录审计元数据。严禁记录 password / token。"""
    return {
        "username": body.username,
        "client_ip": client_ip,
        "client_type": getattr(body, "client_type", None),
        "device_fingerprint": getattr(body, "device_fingerprint", None),
        "game_project_code": getattr(body, "game_project_code", None) or getattr(body, "project_code", None),
        "success": success,
        "reason": reason,
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> LoginResponse:
    """用户登录：D5 限流后交给 AuthService 执行认证链。"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    allowed, count = await incr_rate_limit(
        redis,
        "login",
        client_ip,
        _LOGIN_RATE_LIMIT,
        _LOGIN_RATE_WINDOW,
    )
    if not allowed:
        await create_audit_log(
            db=db,
            actor_type="user",
            actor_id=None,
            action="auth.user.login_failed",
            target_type="user",
            target_id=body.username,
            summary=f"用户 {body.username} 登录失败：请求过于频繁",
            metadata={
                **_login_metadata(body, client_ip=client_ip, success=False, reason="rate_limited"),
                "rate_limit_count": count,
                "rate_limit_max": _LOGIN_RATE_LIMIT,
                "rate_limit_window_seconds": _LOGIN_RATE_WINDOW,
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录请求过于频繁，请稍后再试（{count}/{_LOGIN_RATE_LIMIT} 次/分钟）",
        )

    try:
        result = await login_user(
            body=body,
            client_ip=client_ip,
            db=db,
            redis=redis,
        )
    except HTTPException as exc:
        await create_audit_log(
            db=db,
            actor_type="user",
            actor_id=None,
            action="auth.user.login_failed",
            target_type="user",
            target_id=body.username,
            summary=f"用户 {body.username} 登录失败",
            metadata={
                **_login_metadata(body, client_ip=client_ip, success=False, reason=str(exc.detail)),
                "status_code": exc.status_code,
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        raise

    await create_audit_log(
        db=db,
        actor_type="user",
        actor_id=result.user_id,
        action="auth.user.login_success",
        target_type="user",
        target_id=result.user_id,
        summary=f"用户 {result.username} 登录成功",
        metadata={
            **_login_metadata(body, client_ip=client_ip, success=True),
            "user_id": result.user_id,
            "username": result.username,
            "game_project_id": result.game_project_id,
            "game_project_code": result.game_project_code,
            "authorization_id": result.authorization_id,
            "authorization_level": result.authorization_level,
        },
        ip_address=client_ip,
        user_agent=user_agent,
    )
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """使用 Refresh Token 换取新的 Access Token。"""
    return await refresh_access_token(body=body, db=db, redis=redis)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    """登出：吊销当前 Access Token 并删除对应 Refresh Token。"""
    return await logout_user(
        access_token_str=credentials.credentials,
        body=body,
        redis=redis,
    )


@router.post("/revoke-all", response_model=MessageResponse, summary="踢出所有设备")
async def revoke_all(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    """
    踢出所有 User Refresh Token 会话。

    当前边界:
      1. 删除该用户在 Redis 中的所有 Refresh Token。
      2. 吊销当前 Access Token。
      3. 已签发的其它 Access Token 在自然过期前仍可能有效。

    后续 token_version 落地后，应改为服务端版本号强校验。
    """
    return await revoke_all_devices(
        access_token_str=credentials.credentials,
        redis=redis,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_main_db),
) -> MeResponse:
    """
    获取当前用户在当前项目下的授权摘要。

    当前项目上下文来自 Access Token payload.project。
    授权摘要来自 Authorization，而不是 User 旧字段。
    """
    if current_user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被停用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    game_project_code = _extract_game_project_code(credentials.credentials)

    game_project = await _get_active_game_project_by_code(
        db=db,
        code_name=game_project_code,
    )
    if not game_project:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目不存在或已下线，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    authorization = await _get_active_authorization(
        db=db,
        user_id=current_user.id,
        game_project_id=game_project.id,
    )
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目授权不存在或已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _is_authorization_expired(authorization, datetime.now(timezone.utc)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目授权已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 统计已激活设备数
    from app.models.main.models import DeviceBinding
    activated_result = await db.execute(
        select(func.count(DeviceBinding.id)).where(
            DeviceBinding.user_id == current_user.id,
            DeviceBinding.game_project_id == game_project.id,
            DeviceBinding.status == "active",
        )
    )
    activated_devices = activated_result.scalar_one() or 0
    authorized_devices = int(authorization.authorized_devices or 0)
    inactive_devices = max(authorized_devices - activated_devices, 0) if authorized_devices > 0 else None

    return MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        status=current_user.status,
        game_project_id=game_project.id,
        game_project_code=game_project.code_name,
        authorization_id=authorization.id,
        authorization_level=authorization.user_level,
        authorized_devices=authorized_devices,
        activated_devices=activated_devices,
        inactive_devices=inactive_devices,
        valid_until=authorization.valid_until,
    )


def _extract_game_project_code(access_token: str) -> str:
    """从 Access Token 中读取当前项目 code_name。"""
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    game_project_code = str(payload.get("project_code") or "").strip()
    if not game_project_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少项目上下文，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return game_project_code


async def _get_active_game_project_by_code(
    db: AsyncSession,
    code_name: str,
) -> GameProject | None:
    """按 code_name 读取 active 游戏项目，不存在返回 None（不抛 404）。"""
    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == code_name,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()
