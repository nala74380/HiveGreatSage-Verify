r"""
文件位置: app/routers/auth.py
文件名称: auth.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.1
功能说明:
    认证路由（薄层）：
      POST /api/auth/login    — 登录
      POST /api/auth/refresh  — 刷新 Access Token
      POST /api/auth/logout   — 登出
      GET  /api/auth/me       — 获取当前用户信息

    路由层职责：
      1. 接收 HTTP 请求，提取参数（IP、Header）
      2. 调用 D5 限流检查
      3. 将参数传递给 AuthService，返回结果
      4. 不包含任何业务判断逻辑

改进历史:
    V1.0.1 - 业务逻辑全部迁移至 services/auth_service.py；
             get_current_user 迁移至 core/dependencies.py

调试信息:
    已知问题: 无
    401 Unauthorized：Token 无效/过期/已吊销
    403 Forbidden：账号停用/设备超限/授权问题
    429 Too Many Requests：登录频率超限（D5 限流）
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.redis_client import get_redis, incr_rate_limit
from app.database import get_main_db
from app.models.main.models import User
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
from app.core.security import decode_access_token
from jose import JWTError

router = APIRouter()
_http_bearer = HTTPBearer()

# D5 限流参数（架构设计 D5 决策）
_LOGIN_RATE_LIMIT = 10       # 同 IP 每分钟最多 10 次
_LOGIN_RATE_WINDOW = 60      # 秒


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> LoginResponse:
    """用户登录（D5 限流 → 10步验证链 → 签发 Token）。"""
    client_ip = request.client.host if request.client else "unknown"

    # D5 限流：同 IP 每分钟 ≤ 10 次
    allowed, count = await incr_rate_limit(
        redis, "login", client_ip, _LOGIN_RATE_LIMIT, _LOGIN_RATE_WINDOW
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
    """登出：吊销 AT 并删除 RT。"""
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
    踢出所有设备（T025）。

    操作：
      - 吊销当前 AT（15 分钟内有效的 AT 加入黑名单）
      - 删除该用户在 Redis 中的所有 Refresh Token

    调用后：
      - 所有已登录设备下次使用 RT 刷新时将失败，需重新登录
      - 当前 AT 在剩余有效期（≤15分钟）内仍可使用（JWT 固有限制）

    适用场景：账号被盗、更换设备、安全审计强制下线
    """
    return await revoke_all_devices(
        access_token_str=credentials.credentials,
        redis=redis,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    """获取当前登录用户的基本信息。"""
    try:
        payload = decode_access_token(credentials.credentials)
        game_project_code = payload.get("project", "")
    except JWTError:
        game_project_code = ""

    return MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        user_level=current_user.user_level,
        status=current_user.status,
        game_project_code=game_project_code,
    )