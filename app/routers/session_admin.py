r"""
文件位置: app/routers/session_admin.py
文件名称: session_admin.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    Admin / Agent 后台会话接口。

接口:
    POST /admin/api/session/logout
    POST /api/agents/session/logout

设计目标:
    - 为 Admin / Agent Token 提供服务端吊销能力。
    - 当前 Token 加入 Redis 黑名单，TTL 为 JWT 剩余有效期。
    - 不记录 Token 原文。

边界:
    - 当前仅吊销当前 access_token。
    - 尚未实现”踢出该账号全部后台会话”。
    - User Token 的 token_version 全量吊销已实现（参见 auth_service.revoke_all_devices）。
    - Admin / Agent Token 的全量吊销暂未实现，后续可引入 admin/agent.token_version。
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.redis_client import get_redis, revoke_token
from app.core.security import (
    decode_admin_token,
    decode_agent_token,
    get_access_token_remaining_seconds,
)
from app.schemas.auth import MessageResponse
from app.services.audit_service import create_audit_log
from app.database import get_main_db
from sqlalchemy.ext.asyncio import AsyncSession

admin_router = APIRouter()
agent_router = APIRouter()
_http_bearer = HTTPBearer()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _revoke_backend_token(
    *,
    token: str,
    expected_type: str,
    redis: aioredis.Redis,
) -> tuple[int, str, int]:
    """
    吊销后台 Token。

    Returns:
        actor_id, jti, ttl_seconds
    """
    try:
        payload = decode_admin_token(token) if expected_type == "admin" else decode_agent_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        actor_id = int(payload["sub"])
        jti = str(payload["jti"])
        exp = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 信息无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ttl = get_access_token_remaining_seconds(exp)
    await revoke_token(redis, jti, ttl)
    return actor_id, jti, ttl


@admin_router.post("/logout", response_model=MessageResponse, summary="管理员退出登录")
async def admin_logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> MessageResponse:
    actor_id, _jti, ttl = await _revoke_backend_token(
        token=credentials.credentials,
        expected_type="admin",
        redis=redis,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=actor_id,
        action="auth.admin.logout_success",
        target_type="admin_session",
        target_id=actor_id,
        summary="管理员退出登录并吊销当前 Token",
        metadata={
            "admin_id": actor_id,
            "revoked_current_token": True,
            "ttl_seconds": ttl,
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="管理员已退出登录")


@agent_router.post("/logout", response_model=MessageResponse, summary="代理退出登录")
async def agent_logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> MessageResponse:
    actor_id, _jti, ttl = await _revoke_backend_token(
        token=credentials.credentials,
        expected_type="agent",
        redis=redis,
    )
    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=actor_id,
        action="auth.agent.logout_success",
        target_type="agent_session",
        target_id=actor_id,
        summary="代理退出登录并吊销当前 Token",
        metadata={
            "agent_id": actor_id,
            "revoked_current_token": True,
            "ttl_seconds": ttl,
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="代理已退出登录")
