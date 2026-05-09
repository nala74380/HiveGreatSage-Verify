r"""
文件位置: app/core/dependencies.py
文件名称: dependencies.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.3.0
功能说明:
    FastAPI 全局依赖项。

    本文件提供统一鉴权入口：
      - get_current_user
      - get_game_project_code
      - get_current_admin
      - get_current_agent

    当前鉴权口径:
      1. User Access Token 必须有 jti，并检查 Redis 黑名单。
      2. Admin Token 必须有 jti，并检查 Redis 黑名单。
      3. Agent Token 必须有 jti，并检查 Redis 黑名单。
      4. User 查询必须过滤软删除用户。
      5. Admin / Agent 必须 status=active。

改进历史:
    V1.3.0 (2026-05-09) - get_game_project_code 改为异步并校验 GameProject.is_active。
    V1.2.0 (2026-05-07) - Admin / Agent Token 接入 Redis 黑名单校验。
    V1.1.0 (2026-05-02) - get_current_user 查询用户时统一过滤 User.is_deleted。
    V1.0.1 - 新增 get_game_project_code 依赖，从 JWT 提取游戏项目代码。
    V1.0.0 - 初始版本，从 routers/auth.py 迁移 get_current_user。
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
from app.models.main.models import Admin, Agent, GameProject, User


_http_bearer = HTTPBearer()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _assert_token_not_revoked(
    *,
    payload: dict,
    redis: aioredis.Redis,
    detail: str,
) -> None:
    """统一检查 JWT jti 是否存在且未被 Redis 黑名单吊销。"""
    jti = payload.get("jti")
    if not jti:
        raise _unauthorized("Token 缺少 jti，请重新登录")

    if await is_token_revoked(redis, str(jti)):
        raise _unauthorized(detail)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> User:
    """
    FastAPI 依赖：从 Authorization Header 解析并验证当前用户。

    执行顺序:
      1. 验证 JWT 签名和有效期。
      2. 检查 Redis 黑名单，判断当前 Access Token 是否已登出或被吊销。
      3. 查询用户是否存在、未软删除、状态为 active。
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise _unauthorized("Token 无效或已过期")

    await _assert_token_not_revoked(
        payload=payload,
        redis=redis,
        detail="Token 已被吊销",
    )

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("Token 用户信息无效，请重新登录")

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise _unauthorized("用户不存在或已被停用")

    payload_token_version = int(payload.get("token_version", 0))
    if payload_token_version != int(user.token_version or 0):
        raise _unauthorized("Token 已失效，请重新登录")

    return user


async def get_game_project_code(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> str:
    """
    FastAPI 依赖：从 JWT 中提取当前登录的游戏项目代码名，并校验项目仍处于激活状态。

    校验顺序:
      1. 解码 JWT 提取 project_code。
      2. 查询主库确认 GameProject 存在且 is_active=True。
      3. 通过则返回 code_name，否则 401。

    设计决策:
      - 登录时已校验项目 active，但 Token 有效期内项目可能被管理员停用。
      - 增加主库查询是"纵深防御"——服务层仍有独立的项目状态校验作为第二层。
      - 单次 SELECT 开销可接受（主库连接池 10，333 req/s 峰值）。
    """
    try:
        payload = decode_access_token(credentials.credentials)
        code = str(payload.get("project_code") or "").strip()
        if not code:
            raise _unauthorized("Token 中缺少游戏项目信息，请重新登录")
    except JWTError:
        raise _unauthorized("Token 无效或已过期")

    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == code,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    if not result.scalar_one_or_none():
        raise _unauthorized("游戏项目不存在或已下线，请重新登录")

    return code


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> Admin:
    """
    FastAPI 依赖：验证管理员 Token 并返回 Admin 对象。

    当前规则:
      1. 校验 JWT 签名、有效期、type=admin、jti。
      2. 检查 Redis 黑名单。
      3. 查询 Admin.status 必须为 active。
    """
    try:
        payload = decode_admin_token(credentials.credentials)
    except JWTError:
        raise _unauthorized("管理员 Token 无效或已过期，请重新登录")

    await _assert_token_not_revoked(
        payload=payload,
        redis=redis,
        detail="管理员 Token 已被吊销，请重新登录",
    )

    try:
        admin_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("管理员 Token 信息无效")

    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()

    if not admin or admin.status != "active":
        raise _unauthorized("管理员不存在或已被停用")

    return admin


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> Agent:
    """
    FastAPI 依赖：验证代理 Token 并返回 Agent 对象。

    当前规则:
      1. 校验 JWT 签名、有效期、type=agent、jti。
      2. 检查 Redis 黑名单。
      3. 查询 Agent.status 必须为 active。
    """
    try:
        payload = decode_agent_token(credentials.credentials)
    except JWTError:
        raise _unauthorized("代理 Token 无效或已过期，请重新登录")

    await _assert_token_not_revoked(
        payload=payload,
        redis=redis,
        detail="代理 Token 已被吊销，请重新登录",
    )

    try:
        agent_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized("代理 Token 信息无效")

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent or agent.status != "active":
        raise _unauthorized("代理不存在或已被停用")

    return agent
