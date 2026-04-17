r"""
文件位置: app/routers/auth.py
文件名称: auth.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    认证路由，提供：
      POST /api/auth/login     — 登录（10步验证链）
      POST /api/auth/refresh   — 刷新 Access Token
      POST /api/auth/logout    — 登出（吊销 Token）
      GET  /api/auth/me        — 获取当前用户信息
    路由层只做参数校验和响应组装，业务逻辑委托给 AuthService。
    设备绑定上限（D1 决策）由 AuthService 读取常量 DEVICE_LIMIT_BY_LEVEL。
改进历史: 无
调试信息:
    401 Unauthorized：Token 无效/过期/已吊销。
    403 Forbidden：设备数量超限（DEVICE_LIMIT_EXCEEDED）。
    429 Too Many Requests：登录频率超限（D5 限流）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.config import settings
from app.core.redis_client import (
    delete_refresh_token,
    get_redis,
    get_refresh_token,
    incr_rate_limit,
    is_token_revoked,
    revoke_token,
    store_refresh_token,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_access_token_remaining_seconds,
    get_refresh_token_ttl_seconds,
    verify_password,
)
from app.database import get_main_db
from app.models.main.models import (
    Authorization,
    DeviceBinding,
    GameProject,
    LoginLog,
    User,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MeResponse,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
)
from sqlalchemy import select, func
from datetime import datetime, timezone

router = APIRouter()

# ── 设备绑定上限（D1 决策，按用户级别）──────────────────────
DEVICE_LIMIT_BY_LEVEL: dict[str, int | None] = {
    "trial":  100,
    "normal": 500,
    "vip":    1000,
    "svip":   None,    # None = 无限制
    "tester": None,    # None = 无限制
}


# ── FastAPI 鉴权依赖（供其他路由复用）────────────────────────
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_http_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> User:
    """
    FastAPI 依赖：从 Authorization Header 解析并验证当前用户。
    供所有需要鉴权的路由通过 Depends(get_current_user) 使用。
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

    # 检查黑名单（登出或强制下线）
    jti = payload.get("jti")
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
        )

    return user


# ── POST /login ───────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    用户登录接口（10步验证链）。
    D5 限流：同 IP 每分钟 ≤ 10 次。
    """
    # ── D5 限流检查 ──────────────────────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    allowed, count = await incr_rate_limit(redis, "login", client_ip, limit=10)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录请求过于频繁，请稍后再试（当前：{count}/10 次/分钟）",
        )

    fail_reason: str | None = None
    user: User | None = None
    game_project: GameProject | None = None

    try:
        # Step 1 & 2：用户名存在 + 密码匹配
        result = await db.execute(
            select(User).where(User.username == body.username)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(body.password, user.password_hash):
            fail_reason = "fail_auth"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        # Step 3：账号状态
        if user.status != "active":
            fail_reason = "fail_suspended"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被停用",
            )

        # Step 4：账号到期
        now = datetime.now(timezone.utc)
        if user.expired_at and user.expired_at < now:
            fail_reason = "fail_expired"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已过期",
            )

        # Step 5：通过 project_uuid 查找游戏项目
        result = await db.execute(
            select(GameProject).where(
                GameProject.project_uuid == body.project_uuid,
                GameProject.is_active == True,
            )
        )
        game_project = result.scalar_one_or_none()
        if not game_project:
            fail_reason = "fail_project"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏项目不存在或已下线",
            )

        # Step 6 & 7：授权检查
        result = await db.execute(
            select(Authorization).where(
                Authorization.user_id == user.id,
                Authorization.game_project_id == game_project.id,
                Authorization.status == "active",
            )
        )
        auth = result.scalar_one_or_none()
        if not auth:
            fail_reason = "fail_no_auth"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无此游戏的授权",
            )
        if auth.valid_until and auth.valid_until < now:
            fail_reason = "fail_auth_expired"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="游戏授权已过期",
            )

        # Step 8：设备绑定检查
        result = await db.execute(
            select(DeviceBinding).where(
                DeviceBinding.user_id == user.id,
                DeviceBinding.device_fingerprint == body.device_fingerprint,
                DeviceBinding.status == "active",
            )
        )
        binding = result.scalar_one_or_none()

        if binding:
            # 已绑定：更新最后在线时间
            binding.last_seen_at = now
        else:
            # 新设备：检查绑定数量上限
            limit = DEVICE_LIMIT_BY_LEVEL.get(user.user_level)
            if limit is not None:
                count_result = await db.execute(
                    select(func.count(DeviceBinding.id)).where(
                        DeviceBinding.user_id == user.id,
                        DeviceBinding.status == "active",
                    )
                )
                current_count = count_result.scalar()
                if current_count >= limit:
                    fail_reason = "fail_device_limit"
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"设备绑定数量已达上限（{limit} 台）",
                    )

            # 绑定新设备
            new_binding = DeviceBinding(
                user_id=user.id,
                device_fingerprint=body.device_fingerprint,
                last_seen_at=now,
            )
            db.add(new_binding)

        # Step 9 & 10：签发 Token
        access_token, jti = create_access_token(
            user_id=user.id,
            user_level=user.user_level,
            game_project_code=game_project.code_name,
        )
        refresh_token = create_refresh_token()
        rt_ttl = get_refresh_token_ttl_seconds()

        await store_refresh_token(
            redis=redis,
            user_id=user.id,
            jti=jti,
            rt_value=refresh_token,
            device_fingerprint=body.device_fingerprint,
            ttl_seconds=rt_ttl,
        )

        # 写登录日志（成功）
        db.add(LoginLog(
            user_id=user.id,
            device_fingerprint=body.device_fingerprint,
            ip_address=client_ip,
            client_type=body.client_type,
            game_project_id=game_project.id,
            success=True,
            fail_reason=None,
        ))

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            username=user.username,
            user_level=user.user_level,
            game_project_code=game_project.code_name,
        )

    except HTTPException:
        # 写登录日志（失败）
        if user or fail_reason:
            db.add(LoginLog(
                user_id=user.id if user else None,
                device_fingerprint=body.device_fingerprint,
                ip_address=client_ip,
                client_type=body.client_type,
                game_project_id=game_project.id if game_project else None,
                success=False,
                fail_reason=fail_reason or "fail_unknown",
            ))
        raise


# ── POST /refresh ─────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """使用 Refresh Token 换取新的 Access Token（RT 本身不变）。"""
    # RT 是不透明字符串，必须结合 user_id + jti 从 Redis 验证
    # 客户端需要传 refresh_token 原始值，服务端通过扫描 Redis 验证
    # 简化方案：客户端同时传 refresh_token，服务端用 SCAN 查找匹配
    # TODO: Phase 2 优化为客户端传 user_id + jti，避免 SCAN

    # 临时实现：通过 scan 查找匹配的 RT
    found_data: dict | None = None
    async for key in redis.scan_iter("refresh:*"):
        raw = await redis.get(key)
        if raw:
            import json
            data = json.loads(raw)
            if data.get("rt_value") == body.refresh_token:
                found_data = data
                break

    if not found_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
        )

    user_id = found_data["user_id"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被停用",
        )

    # 从 payload 获取 game_project_code（RT 中不含，需从 found_data 或其他方式获取）
    # 简化：从用户最近授权中取（Phase 2 完善）
    # TODO: RT 存储时一并存入 game_project_code
    game_project_code = found_data.get("game_project_code", "")

    access_token, new_jti = create_access_token(
        user_id=user.id,
        user_level=user.user_level,
        game_project_code=game_project_code,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── POST /logout ──────────────────────────────────────────────
@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
):
    """登出：吊销当前 Access Token 并删除 Refresh Token。"""
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        jti = payload.get("jti", "")
        exp = payload.get("exp", 0)
        user_id = int(payload.get("sub", 0))

        # 将 AT 加入黑名单
        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)

        # 删除 RT
        await delete_refresh_token(redis, user_id, jti)

    except JWTError:
        pass  # Token 已过期也允许登出

    return MessageResponse(message="登出成功")


# ── GET /me ───────────────────────────────────────────────────
@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
):
    """获取当前登录用户的基本信息。"""
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
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