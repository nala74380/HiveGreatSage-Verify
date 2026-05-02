r"""
文件位置: app/routers/auth.py
文件名称: auth.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    认证路由薄层：
      POST /api/auth/login      — 登录
      POST /api/auth/refresh    — 刷新 Access Token
      POST /api/auth/logout     — 登出
      POST /api/auth/revoke-all — 踢出所有 User Refresh Token 会话
      GET  /api/auth/me         — 获取当前用户在当前项目下的授权摘要

    本次整改边界:
      1. /api/auth/me 不再返回旧 User.user_level 作为授权等级。
      2. /api/auth/me 从 Token 的 project 字段读取当前项目上下文。
      3. /api/auth/me 重新查询 GameProject + Authorization。
      4. /api/auth/me 返回 Authorization.user_level / authorized_devices / valid_until。
      5. /api/auth/me 对软删除用户直接拒绝。

    当前仍保留的历史边界:
      1. 登录响应 LoginResponse 仍返回 user_level / game_project_code。
      2. Access Token payload 仍使用 level / project 字段。
      3. 这些字段后续单独做 token/schema 收口。

改进历史:
    V1.1.0 (2026-05-02) - /me 改为 Authorization 授权摘要口径。
    V1.0.1 - 业务逻辑迁移至 services/auth_service.py。
    V1.0.0 - 初始版本。
"""

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.redis_client import get_redis, incr_rate_limit
from app.core.security import decode_access_token
from app.database import get_main_db
from app.models.main.models import Authorization, GameProject, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MeResponse,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import (
    login_user,
    logout_user,
    refresh_access_token,
    revoke_all_devices,
)


router = APIRouter()
_http_bearer = HTTPBearer()

_LOGIN_RATE_LIMIT = 10
_LOGIN_RATE_WINDOW = 60


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> LoginResponse:
    """用户登录：D5 限流后交给 AuthService 执行认证链。"""
    client_ip = request.client.host if request.client else "unknown"

    allowed, count = await incr_rate_limit(
        redis,
        "login",
        client_ip,
        _LOGIN_RATE_LIMIT,
        _LOGIN_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录请求过于频繁，请稍后再试（{count}/{_LOGIN_RATE_LIMIT} 次/分钟）",
        )

    return await login_user(
        body=body,
        client_ip=client_ip,
        db=db,
        redis=redis,
    )


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

    if _is_authorization_expired(authorization.valid_until):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目授权已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        status=current_user.status,
        game_project_id=game_project.id,
        game_project_code=game_project.code_name,
        authorization_id=authorization.id,
        authorization_level=authorization.user_level,
        authorized_devices=authorization.authorized_devices,
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
    """按 code_name 读取 active 游戏项目。"""
    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == code_name,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _get_active_authorization(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
) -> Authorization | None:
    """读取当前用户在当前项目下的 active 授权。"""
    result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user_id,
            Authorization.game_project_id == game_project_id,
            Authorization.status == "active",
        )
    )
    return result.scalar_one_or_none()


def _is_authorization_expired(valid_until: datetime | None) -> bool:
    """判断授权是否过期，兼容数据库返回 naive datetime 的情况。"""
    if valid_until is None:
        return False

    normalized_valid_until = valid_until
    if normalized_valid_until.tzinfo is None:
        normalized_valid_until = normalized_valid_until.replace(tzinfo=timezone.utc)

    return normalized_valid_until < datetime.now(timezone.utc)
