r"""
文件位置: app/services/auth_service.py
文件名称: auth_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    认证服务层，包含全部认证业务逻辑：
      - login_user()           用户登录
      - refresh_access_token() Refresh Token 刷新 Access Token
      - revoke_all_devices()   踢出所有 User Token 会话
      - logout_user()          用户登出

    本次整改边界:
      1. 用户登录必须过滤软删除用户。
      2. Refresh Token 刷新必须过滤软删除用户。
      3. 用户登录以 Authorization.valid_until 作为项目授权有效期判断。
      4. Refresh Token 刷新不再读取 User.user_level。
      5. Refresh Token 刷新必须重新校验项目与 Authorization。
      6. Access Token 中的 user_level 来自 Authorization.user_level。

    当前仍保留的历史字段边界:
      1. LoginResponse 仍返回 user_level / game_project_code。
      2. Access Token 当前仍写入 user_level / game_project_code。
      3. 这些字段属于后续 schema / token payload 收口任务，本文件本轮不扩展响应结构。

    关联文档:
      [[01-网络验证系统/架构设计]]
      [[01-网络验证系统/API鉴权方案]]
      [[01-网络验证系统/旧字段旧接口清理清单]]

改进历史:
    V1.1.0 (2026-05-02) - 登录与刷新过滤软删除用户；刷新改用 Authorization.user_level。
    V1.0.1 - 设备绑定改为用户 × 项目 × 设备维度，设备上限改用 Authorization.authorized_devices。
    V1.0.0 - 初始版本，从 routers/auth.py 迁移全部业务逻辑。

调试信息:
    已知问题:
      1. LoginResponse / Token payload 仍保留旧字段名 user_level / game_project_code。
      2. Admin / Agent Token 尚未接入服务端吊销闭环。
      3. token_version 尚未落地。
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


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def login_user(
    body: LoginRequest,
    client_ip: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> LoginResponse:
    """
    用户登录。

    当前验证链：
      Step 1  用户名存在，且用户未软删除
      Step 2  密码匹配
      Step 3  账号状态 active
      Step 4  project_uuid 对应的游戏项目存在且激活
      Step 5  该用户对该项目有 active 授权记录
      Step 6  授权未到期
      Step 7  Android 设备绑定检查
      Step 8  签发 AT + RT
      Step 9  写成功登录日志
      Step 10 返回登录响应

    失败时写登录日志（独立 Session，不受主事务回滚影响）。
    D5 限流由 router 层在调用前执行。

    重要边界：
      授权有效期统一以 Authorization.valid_until 为准。
    """
    fail_reason: str | None = None
    user: User | None = None
    game_project: GameProject | None = None

    try:
        # Step 1 & 2：用户名 + 密码 + 软删除过滤
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

        # Step 3：账号状态
        if user.status != "active":
            fail_reason = "fail_suspended"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被停用",
            )

        now = datetime.now(timezone.utc)

        # Step 4：游戏项目存在且激活
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

        # Step 5：授权记录存在
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

        # Step 6：授权未到期
        if _is_authorization_expired(auth, now):
            fail_reason = "fail_auth_expired"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="游戏授权已过期",
            )

        # Step 7：设备绑定检查
        # PC 中控（client_type="pc"）登录不创建设备绑定，不占用安卓设备名额。
        # Android 脚本按“用户 × 项目 × 设备”维度绑定。
        # 设备上限来自当前项目授权 Authorization.authorized_devices：
        #   0 表示不限设备数；>0 表示当前项目最多可绑定 N 台 active Android 设备。
        if body.client_type == "android":
            result = await db.execute(
                select(DeviceBinding).where(
                    DeviceBinding.user_id == user.id,
                    DeviceBinding.game_project_id == game_project.id,
                    DeviceBinding.device_fingerprint == body.device_fingerprint,
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

                db.add(
                    DeviceBinding(
                        user_id=user.id,
                        game_project_id=game_project.id,
                        device_fingerprint=body.device_fingerprint,
                        last_seen_at=now,
                        status="active",
                    )
                )

        # Step 8：签发 Token
        access_token, jti = create_access_token(
            user_id=user.id,
            authorization_level=auth.user_level,
            game_project_code=game_project.code_name,
        )
        refresh_token = create_refresh_token()
        rt_ttl = get_refresh_token_ttl_seconds()

        await store_refresh_token_v2(
            redis=redis,
            user_id=user.id,
            jti=jti,
            rt_value=refresh_token,
            device_fingerprint=body.device_fingerprint,
            game_project_code=game_project.code_name,
            ttl_seconds=rt_ttl,
        )

        # Step 9：写成功日志（在主事务内，随 commit 一起落库）
        db.add(
            _build_login_log(
                user_id=user.id,
                device_fingerprint=body.device_fingerprint,
                ip_address=client_ip,
                client_type=body.client_type,
                game_project_id=game_project.id,
                success=True,
                fail_reason=None,
            )
        )

        # Step 10：返回
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            username=user.username,
            authorization_level=auth.user_level,
            game_project_code=game_project.code_name,
        )

    except HTTPException:
        await _write_login_log(
            user_id=user.id if user else None,
            device_fingerprint=body.device_fingerprint,
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
    """
    使用 Refresh Token 换取新的 Access Token。

    当前规则：
      1. 通过 RT 反查索引 O(1) 定位 RT 数据，不做 SCAN。
      2. 用户必须存在、未软删除、状态 active。
      3. RT 中的 game_project_code 必须能找到 active GameProject。
      4. 用户必须仍拥有该项目 active Authorization。
      5. Authorization.valid_until 未过期。
      6. 新 Access Token 的 user_level 来自 Authorization.user_level。

    重要整改：
      Refresh Token 刷新不得再读取 User.user_level。
    """
    rt_data = await get_refresh_token_by_value(redis, body.refresh_token)
    if rt_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
        )

    user_id: int = int(rt_data["user_id"])
    game_project_code: str = str(rt_data.get("game_project_code") or "").strip()

    if not game_project_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 缺少项目上下文",
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

    access_token, _ = create_access_token(
        user_id=user.id,
        authorization_level=auth.user_level,
        game_project_code=game_project.code_name,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def revoke_all_devices(
    access_token_str: str,
    redis: aioredis.Redis,
) -> MessageResponse:
    """
    踢出所有 User Token 会话。

    操作：
      1. 吊销当前 AT（加黑名单，TTL = 剩余有效期）
      2. 用 SCAN 删除该用户在 Redis 中的所有 RT
         Key 模式：refresh:{user_id}:*
      3. 因为 RT 反查索引（rt_lookup:{hash}）TTL 与主 Key 一致，
         主 Key 删除后反查索引会在自然过期时自动消失，
         不额外删除反查索引（避免 O(n) SCAN rt_lookup:*）

    安全说明：
      该用户所有已签发的 AT 在过期前仍然有效（黑名单只记录了当前这一个）。
      这是 Stateless JWT 的固有限制。
      后续 token_version 落地后，应改为服务端版本号强校验。
    """
    try:
        payload = decode_access_token(access_token_str)
        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)
        user_id: int = int(payload.get("sub", 0))

        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)

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
    """
    登出：将 AT 加入黑名单，并删除对应 RT 及其反查索引。

    AT 已过期时也允许正常登出（直接跳过黑名单写入）。
    """
    try:
        payload = decode_access_token(access_token_str)
        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)
        user_id: int = int(payload.get("sub", 0))

        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)

        await delete_refresh_token_v2(
            redis=redis,
            user_id=user_id,
            jti=jti,
            rt_value=body.refresh_token,
        )

    except JWTError:
        pass

    return MessageResponse(message="登出成功")


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_active_authorization(
    db: AsyncSession,
    user_id: int,
    game_project_id: int,
) -> Authorization | None:
    """读取用户在指定项目下的 active 授权。"""
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
    """
    判断授权是否过期。

    兼容数据库返回 naive datetime 的情况：
    PostgreSQL 存储带时区的 timestamp，但 ORM 加载时可能丢失 tzinfo。
    对 naive datetime 统一视为 UTC，避免 TypeError。
    """
    if auth.valid_until is None:
        return False

    valid_until = auth.valid_until
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)

    return valid_until < now


def _build_login_log(
    user_id: int | None,
    device_fingerprint: str,
    ip_address: str,
    client_type: str,
    game_project_id: int | None,
    success: bool,
    fail_reason: str | None,
) -> LoginLog:
    """构造 LoginLog ORM 对象（不执行写入，由调用方决定 Session）。"""
    return LoginLog(
        user_id=user_id,
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        client_type=client_type,
        game_project_id=game_project_id,
        success=success,
        fail_reason=fail_reason,
    )


async def _write_login_log(
    user_id: int | None,
    device_fingerprint: str,
    ip_address: str,
    client_type: str,
    game_project_id: int | None,
    success: bool,
    fail_reason: str | None,
) -> None:
    """
    用独立 Session 写登录日志。

    独立 Session 与主登录事务完全隔离：
    主事务因校验失败而回滚时，失败日志仍能正常落库。
    """
    log = _build_login_log(
        user_id=user_id,
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        client_type=client_type,
        game_project_id=game_project_id,
        success=success,
        fail_reason=fail_reason,
    )
    async with _main_session_factory() as session:
        session.add(log)
        await session.commit()
