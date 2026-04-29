r"""
文件位置: app/services/auth_service.py
文件名称: auth_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    认证服务层，包含全部认证业务逻辑：
      - login_user()          登录（10步验证链，D1 设备绑定上限）
      - refresh_access_token() 刷新 AT（O(1) RT 反查，无 SCAN）
      - logout_user()          登出（AT 加黑名单 + 删除 RT）

    设计要点：
      1. 本层不接触 HTTP 概念（不导入 Request/Response），
         只接受数据对象，返回数据对象，由 router 层转换为 HTTP 响应。
      2. 登录日志写入使用独立 Session（_write_login_log），
         与主登录事务隔离，确保失败日志不被主事务回滚。
      3. 设备绑定上限由 DEVICE_LIMIT_BY_LEVEL 常量控制（D1 决策）。

    关联文档: [[01-网络验证系统/架构设计]] [[01-网络验证系统/API鉴权方案]]

改进历史:
    V1.0.0 - 初始版本，从 routers/auth.py 迁移全部业务逻辑

调试信息:
    已知问题: 无
    TODO(P1): 数据库查询逐步迁移到 repositories 层（当前直接在 service 内查询）
"""

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import (
    delete_all_refresh_tokens,
    delete_refresh_token_v2,
    get_refresh_token_by_value,
    incr_rate_limit,
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
from app.config import settings

# ── D1 决策：设备绑定上限（按用户级别）───────────────────────
# None 表示无限制（svip / tester 跳过数量检查）
DEVICE_LIMIT_BY_LEVEL: dict[str, int | None] = {
    "trial":  100,
    "normal": 500,
    "vip":    1000,
    "svip":   None,
    "tester": None,
}


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
    用户登录（10步验证链）。

    验证链：
      Step 1  用户名存在
      Step 2  密码匹配
      Step 3  账号状态 active
      Step 4  账号未到期
      Step 5  project_uuid 对应的游戏项目存在且激活
      Step 6  该用户对该项目有授权记录
      Step 7  授权未到期
      Step 8  设备绑定检查（已绑定→更新；新设备→检查上限→绑定）
      Step 9  写登录日志（成功）
      Step 10 签发 AT + RT，存 Redis，返回

    失败时写登录日志（独立 Session，不受主事务回滚影响）。
    D5 限流由 router 层在调用前执行。
    """
    fail_reason: str | None = None
    user: User | None = None
    game_project: GameProject | None = None

    try:
        # Step 1 & 2：用户名 + 密码
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

        # Step 5：游戏项目存在且激活
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

        # Step 6：授权记录存在
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

        # Step 7：授权未到期
        if auth.valid_until and auth.valid_until < now:
            fail_reason = "fail_auth_expired"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="游戏授权已过期",
            )

        # Step 8：设备绑定检查
        # PC 中控（client_type="pc"）登录不创建设备绑定，不占用激活名额
        # 设备绑定只针对安卓脚本（client_type="android"）
        if body.client_type == "android":
            result = await db.execute(
                select(DeviceBinding).where(
                    DeviceBinding.user_id == user.id,
                    DeviceBinding.device_fingerprint == body.device_fingerprint,
                    DeviceBinding.status == "active",
                )
            )
            binding = result.scalar_one_or_none()

            if binding:
                # 已绑定设备：更新最后在线时间
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
                    current_count = count_result.scalar_one()
                    if current_count >= limit:
                        fail_reason = "fail_device_limit"
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"设备绑定数量已达上限（{limit} 台）",
                        )
                new_binding = DeviceBinding(
                    user_id=user.id,
                    device_fingerprint=body.device_fingerprint,
                    last_seen_at=now,
                    status="active",
                )
                db.add(new_binding)
        # PC 中控：跳过绑定，直接进入 Step 9 签发 Token

        # Step 9 & 10：签发 Token
        access_token, jti = create_access_token(
            user_id=user.id,
            user_level=user.user_level,
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

        # 写成功日志（在主事务内，随 commit 一起落库）
        db.add(_build_login_log(
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
        # 失败日志用独立 Session 写入，不受主事务回滚影响
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

    通过 RT 反查索引 O(1) 定位 RT 数据，不做 SCAN 全表扫描。
    RT 本身有效期内可多次使用（Phase 1 不做滚动刷新）。
    """
    rt_data = await get_refresh_token_by_value(redis, body.refresh_token)
    if rt_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
        )

    user_id: int = rt_data["user_id"]
    game_project_code: str = rt_data.get("game_project_code", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被停用",
        )

    access_token, _ = create_access_token(
        user_id=user.id,
        user_level=user.user_level,
        game_project_code=game_project_code,
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
    踢出所有设备（T025）。

    操作：
      1. 吊销当前 AT（加黑名单，TTL = 剩余有效期）
      2. 用 SCAN 删除该用户在 Redis 中的所有 RT
         Key 模式：refresh:{user_id}:*
      3. 因为 RT 反查索引（rt_lookup:{hash}）TTL 与主 Key 一致，
         主 Key 删除后反查索引会在自然过期时自动消失，
         不额外删除反查索引（避免 O(n) SCAN rt_lookup:*）

    安全说明：
      该用户所有已签发的 AT 在过期前仍然有效（黑名单只记录了当前这一个）。
      这是 Stateless JWT 的固有限制——AT 最多 15 分钟自动失效。
      如需即时完全失效，Phase 3 可引入 per-user 版本号机制。
    """
    try:
        payload = decode_access_token(access_token_str)
        jti: str = payload.get("jti", "")
        exp: int = payload.get("exp", 0)
        user_id: int = int(payload.get("sub", 0))

        # 吊销当前 AT
        remaining = get_access_token_remaining_seconds(exp)
        await revoke_token(redis, jti, remaining)

        # 删除该用户所有 RT
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

        # 删除 RT 主 Key + 反查索引
        await delete_refresh_token_v2(
            redis=redis,
            user_id=user_id,
            jti=jti,
            rt_value=body.refresh_token,
        )

    except JWTError:
        # AT 已过期也允许登出，静默处理
        pass

    return MessageResponse(message="登出成功")


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

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