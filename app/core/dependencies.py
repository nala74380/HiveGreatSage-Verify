r"""
文件位置: app/core/dependencies.py
文件名称: dependencies.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.1
功能说明:
    FastAPI 全局依赖项。
    将 get_current_user 从 routers/auth.py 中剥离到此处，
    使所有需要鉴权的路由都能通过统一入口导入，避免循环依赖。

    使用方式：
        from app.core.dependencies import get_current_user

        @router.get("/some-endpoint")
        async def some_endpoint(
            current_user: User = Depends(get_current_user),
        ):
            ...

改进历史:
    V1.0.1 - 新增 get_game_project_code 依赖，从 JWT 提取游戏项目代码，
             供 device 等需要访问游戏库的路由使用
    V1.0.0 - 初始版本，从 routers/auth.py 迁移 get_current_user
调试信息:
    已知问题: 无
    Token 校验失败返回 401；用户被停用返回 401。
"""

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis, is_token_revoked
from app.core.security import (
    decode_access_token,
    decode_admin_token,
    decode_agent_token,
)
from app.database import get_main_db
from app.models.main.models import Admin, Agent, User

_http_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> User:
    """
    FastAPI 依赖：从 Authorization Header 解析并验证当前用户。

    执行顺序：
      1. 验证 JWT 签名和有效期
      2. 检查 Redis 黑名单（是否已登出或被强制下线）
      3. 查询用户是否存在且状态为 active

    返回已验证的 User ORM 对象，供业务逻辑使用。
    任一步骤失败均返回 HTTP 401。
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti: str | None = payload.get("jti")
    if jti and await is_token_revoked(redis, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已被吊销",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被停用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_game_project_code(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> str:
    """
    FastAPI 依赖：从 JWT 中提取当前登录的游戏项目代码名（code_name）。

    登录时签发的 AT 中已包含 'project' 字段，无需再次查询数据库。
    device / params / update 等需要知道游戏库的路由层使用此依赖。
    """
    try:
        payload = decode_access_token(credentials.credentials)
        code = payload.get("project", "")
        if not code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 中缺少游戏项目信息，请重新登录",
            )
        return code
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> Admin:
    """
    FastAPI 依赖：验证管理员 Token 并返回 Admin 对象。
    管理后台和代理管理接口通过此依赖鉴权。
    """
    try:
        payload = decode_admin_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员 Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin_id = int(payload["sub"])
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()

    if not admin or admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员不存在或已被停用",
        )
    return admin


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> Agent:
    """
    FastAPI 依赖：验证代理 Token 并返回 Agent 对象。
    代理专属接口通过此依赖鉴权。
    """
    try:
        payload = decode_agent_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="代理 Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    agent_id = int(payload["sub"])
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent or agent.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="代理不存在或已被停用",
        )
    return agent