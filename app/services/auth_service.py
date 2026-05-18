r"""
文件位置: app/services/auth_service.py
文件名称: auth_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-18
版本: V1.6.0
功能说明:
    认证服务层，包含全部认证业务逻辑：
      - login_user()           用户登录
      - refresh_access_token() Refresh Token 刷新 Access Token
      - revoke_all_devices()   踢出所有 User Token 会话
      - logout_user()          用户登出

    当前设备口径:
      1. 用户登录必须过滤软删除用户。
      2. Refresh Token 刷新必须过滤软删除用户。
      3. 用户登录以 Authorization.valid_until 作为项目授权有效期判断。
      4. Refresh Token 刷新不再读取 User.user_level。
      5. Refresh Token 刷新必须重新校验项目与 Authorization。
      6. Access Token 中的 authorization_level 来自 Authorization.user_level。
      7. Access Token 项目字段统一为 project_code。
      8. Android 首次创建设备绑定时写入 audit_log。
      9. 设备绑定审计记录设备编号。
      10. LoginLog 当前直接写入 device_id。

    当前字段口径:
      1. LoginResponse 返回 authorization_level / game_project_code。
      2. Token payload 返回 authorization_level / project_code。
      3. User.user_level / max_devices / expired_at 不再作为业务字段。

改进历史:
    V1.7.0 (2026-05-18) - 设备绑定统一改为账号 + 项目 + 设备编号。
    V1.2.0 (2026-05-07) - Android 首次创建设备绑定接入 audit_log。
    V1.1.0 (2026-05-02) - 登录与刷新过滤软删除用户；刷新改用 Authorization.user_level。
    V1.0.1 - 设备绑定改为用户 × 项目 × 设备维度，设备上限改用 Authorization.authorized_devices。
    V1.0.0 - 初始版本，从 routers/auth.py 迁移全部业务逻辑。
"""

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_client import (
    delete_all_refresh_tokens,
    delete_refresh_token_v2,
    get_refresh_token_by_value,
    revoke_token,
    store_refresh_token_v2,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_access_token_remaining_seconds,
    get_refresh_token_ttl_seconds,
    verify_password,
)
from app.database import _main_session_factory
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
    MessageResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services.audit_service import create_audit_log


async def login_user(
    body: LoginRequest,
    client_ip: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> LoginResponse:
    fail_reason: str | None = None
    user: User | None = None
    game_project: GameProject | None = None

    try:
        result = await db.execute(
            select(User).where(
                User.username == body.username,
                User.is_deleted == False,  # noqa: E712
            )
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(body.password, user.password_hash):
            fail_reason = "fail_auth"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        if user.status != "active":
            fail_reason = "fail_suspended"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被停用",
            )

        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(GameProject).where(
                GameProject.project_uuid == body.project_uuid,
                GameProject.is_active == True,  # noqa: E712
            )
        )
        game_project = result.scalar_one_or_none()
        if not game_project:
            fail_reason = "fail_project"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="游戏项目不存在或已下线",
            )

        auth = await _get_active_authorization(
            db=db,
            user_id=user.id,
            game_project_id=game_project.id,
        )
        if not auth:
            fail_reason = "fail_no_auth"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无此游戏的授权",
            )

        if _is_authorization_expired(auth, now):
            fail_reason = "fail_auth_expired"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="游戏授权已过期",
            )

        if body.client_type == "android":
            result = await db.execute(
                select(DeviceBinding).where(
                    DeviceBinding.user_id == user.id,
                    DeviceBinding.game_project_id == game_project.id,
                    DeviceBinding.device_id == body.device_id,
                    DeviceBinding.status == "active",
                )
            )
            binding = result.scalar_one_or_none()

            if binding:
                binding.last_seen_at = now
            else:
                limit = int(auth.authorized_devices or 0)
                if limit > 0:
                    count_result = await db.execute(
                        select(func.count(DeviceBinding.id)).where(
                            DeviceBinding.user_id == user.id,
                            DeviceBinding.game_project_id == game_project.id,
                            DeviceBinding.status == "active",
                        )
                    )
                    current_count = int(count_result.scalar_one() or 0)
                    if current_count >= limit:
                        fail_reason = "fail_device_limit"
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"当前项目设备绑定数量已达上限（{limit} 台）",
                        )

                new_binding = DeviceBinding(
                    user_id=user.id,
                    game_project_id=game_project.id,
                    device_id=body.device_id,
                    last_seen_at=now,
                    status="active",
                )
                db.add(new_binding)
                await db.flush()

                await create_audit_log(
                    db=db,
                    actor_type="user",
                    actor_id=user.id,
                    action="device_binding.bind",
                    target_type="device_binding",
                    target_id=new_binding.id,
                    summary=f"用户 {user.id} 绑定项目 {game_project.code_name} 设备",
                    metadata={
                        "binding_id": new_binding.id,
                        "user_id": user.id,
                        "username": user.username,
                        "game_project_id": game_project.id,
                        "game_project_code": game_project.code_name,
                        "device_id": body.device_id,
                        "client_type": body.client_type,
                        "authorized_devices": int(auth.authorized_devices or 0),
                    },
                    ip_address=client_ip,
                )

        access_token, jti = create_access_token(
            user_id=user.id,
            authorization_level=auth.user_level,
            game_project_code=game_project.code_name,
            token_version=user.token_version,
        )
        refresh_token = create_refresh_token()
        rt_ttl = get_refresh_token_ttl_seconds()

        await store_refresh_token_v2(
            redis=redis,
            user_id=user.id,
            jti=jti,
            rt_value=refresh_token,
            device_id=body.device_id,
            client_type=body.client_type,
            game_project_code=game_project.code_name,
            token_version=user.token_version,
            ttl_seconds=rt_ttl,
        )

        db.add(
            _build_login_log(
                user_id=user.id,
                device_id=body.device_id,
                ip_address=client_ip,
                client_type=body.client_type,
                game_project_id=game_project.id,
                success=True,
                fail_reason=None,
            )
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            username=user.username,
            game_project_id=game_project.id,
            authorization_id=auth.id,
            authorization_level=auth.user_level,
            game_project_code=game_project.code_name,
        )

    except HTTPException:
        await _write_login_log(
            user_id=user.id if user else None,
            device_id=body.device_id,
            ip_address=client_ip,
            client_type=body.client_type,
            game_project_id=game_project.id if game_project else None,
            success=False,
            fail_reason=fail_reason or "fail_unknown",
        )
        raise


async def refresh_access_token(
    body: RefreshRequest,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> TokenResponse:
    rt_data = await get_refresh_token_by_value(redis, body.refresh_token)
    if rt_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
        )

    user_id: int = int(rt_data["user_id"])
    old_jti: str = str(rt_data["jti"])
    game_project_code: str = str(rt_data.get("game_project_code") or "").strip()
    rt_device_id: str = str(rt_data.get("device_id") or "")
    rt_client_type: str = str(rt_data.get("client_type") or "")
    rt_token_version: int = int(rt_data.get("token_version", 0))

    if not game_project_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 缺少项目上下文",
        )

    if rt_device_id != body.device_id or rt_client_type != body.client_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 与当前设备不匹配",
        )

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被停用",
        )

    if rt_token_version != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 已失效，请重新登录",
        )

    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == game_project_code,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    game_project = result.scalar_one_or_none()

    if not game_project:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目不存在或已下线",
        )

    auth = await _get_active_authorization(
        db=db,
        user_id=user.id,
        game_project_id=game_project.id,
    )
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目授权不存在或已失效",
        )

    now = datetime.now(timezone.utc)
    if _is_authorization_expired(auth, now):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="项目授权已过期",
        )

    access_token, new_jti = create_access_token(
        user_id=user.id,
        authorization_level=auth.user_level,
        game_project_code=game_project.code_name,
        token_version=user.token_version,
    )
    new_refresh_token = create_refresh_token()
    rt_ttl = get_refresh_token_ttl_seconds()

    await delete_refresh_token_v2(
        redis=redis,
        user_id=user.id,
        jti=old_jti,
        rt_value=body.refresh_token,
    )
    await store_refresh_token_v2(
        redis=redis,
        user_id=user.id,
        jti=new_jti,
        rt_value=new_refresh_token,
        device_id=body.device_id,
        client_type=body.client_type,
        game_project_code=game_project.code_name,
        token_version=user.token_version,
        ttl_seconds=rt_ttl,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def revoke_all_devices(
    access_token_str: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> MessageResponse:
    try:
        payload = decode_access_token(access_token_str)
        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)
        user_id: int = int(payload.get("sub", 0))

        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)

        result = await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_deleted == False,  # noqa: E712
            )
        )
        user = result.scalar_one_or_none()
        if not user or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已被停用",
            )

        user.token_version = int(user.token_version or 0) + 1
        await db.flush()

        deleted_count = await delete_all_refresh_tokens(redis, user_id)

        return MessageResponse(
            message=f"已踢出所有设备，共清除 {deleted_count} 个活跃会话"
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


async def logout_user(
    access_token_str: str,
    body: LogoutRequest,
    redis: aioredis.Redis,
) -> MessageResponse:
    try:
        payload = decode_access_token(access_token_str)
        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)

        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)
    except JWTError:
        pass

    rt_data = await get_refresh_token_by_value(redis, body.refresh_token)
    if rt_data is not None:
        await delete_refresh_token_v2(
            redis=redis,
            user_id=int(rt_data["user_id"]),
            jti=str(rt_data["jti"]),
            rt_value=body.refresh_token,
        )

    return MessageResponse(message="登出成功")


async def _get_active_authorization(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
) -> Authorization | None:
    result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user_id,
            Authorization.game_project_id == game_project_id,
            Authorization.status == "active",
        )
    )
    return result.scalar_one_or_none()


def _is_authorization_expired(
    auth: Authorization,
    now: datetime,
) -> bool:
    if auth.valid_until is None:
        return False

    valid_until = auth.valid_until
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)

    return valid_until < now


def _build_login_log(
    user_id: int | None,
    device_id: str,
    ip_address: str,
    client_type: str,
    game_project_id: int | None,
    success: bool,
    fail_reason: str | None,
) -> LoginLog:
    return LoginLog(
        user_id=user_id,
        device_id=device_id,
        ip_address=ip_address,
        client_type=client_type,
        game_project_id=game_project_id,
        success=success,
        fail_reason=fail_reason,
    )


async def _write_login_log(
    user_id: int | None,
    device_id: str,
    ip_address: str,
    client_type: str,
    game_project_id: int | None,
    success: bool,
    fail_reason: str | None,
) -> None:
    log = _build_login_log(
        user_id=user_id,
        device_id=device_id,
        ip_address=ip_address,
        client_type=client_type,
        game_project_id=game_project_id,
        success=success,
        fail_reason=fail_reason,
    )
    async with _main_session_factory() as session:
        session.add(log)
        await session.commit()
