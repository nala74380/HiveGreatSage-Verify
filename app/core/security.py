r"""
文件位置: app/core/security.py
文件名称: security.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    安全模块，提供两类功能：
      1. 密码哈希：使用 bcrypt，verify_password / hash_password
      2. JWT 管理：
         - Access Token（15分钟，含 sub/level/project/jti）
         - Refresh Token（不透明字符串，存 Redis，7天）
         - 校验 AT：decode_access_token
    所有有效期从 config.settings 读取，不硬编码。
改进历史: 无
调试信息:
    JWT 解码失败（JWTError）通常是 SECRET_KEY 不一致或 Token 格式错误。
    bcrypt 版本兼容性：passlib[bcrypt] 与 bcrypt>=4.0 配合使用。
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── 常量 ──────────────────────────────────────────────────────
ALGORITHM = "HS256"

# ── 密码哈希上下文（bcrypt）───────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """将明文密码哈希为 bcrypt 字符串，存入数据库。"""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码是否与数据库中的哈希值匹配。"""
    return _pwd_context.verify(plain_password, hashed_password)


# ── Access Token ──────────────────────────────────────────────

def create_access_token(
    user_id: int,
    user_level: str,
    game_project_code: str,
) -> tuple[str, str]:
    """
    签发 Access Token（JWT，HS256，15分钟有效期）。

    Payload 字段（与 API鉴权方案.md 对齐）：
        sub     : str(user_id)
        level   : user_level（'trial'/'normal'/'vip'/'svip'/'tester'）
        project : game_project.code_name
        jti     : UUID v4，用于黑名单校验
        iat     : 签发时间
        exp     : 过期时间

    返回：
        (token_string, jti) — jti 需要与 Refresh Token 关联存入 Redis
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "level": user_level,
        "project": game_project_code,
        "jti": jti,
        "iat": now,
        "exp": expire,
        "type": "access",
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码并验证 Access Token。

    返回 payload 字典（已验证签名和有效期）。
    失败时抛出 JWTError（由调用方转换为 HTTP 401）。
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    # 类型检查：确保是 access token，不接受 refresh token 当作 access token
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")

    return payload


# ── Refresh Token ─────────────────────────────────────────────

def create_refresh_token() -> str:
    """
    生成不透明的 Refresh Token（URL-safe 随机字符串，48字节 = 64字符）。
    RT 本身不携带信息，所有状态存在 Redis 中（Key: refresh:{user_id}:{jti}）。
    """
    return secrets.token_urlsafe(48)


def get_refresh_token_ttl_seconds() -> int:
    """返回 Refresh Token 的 TTL（秒），从配置读取。"""
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


# ── 工具函数 ──────────────────────────────────────────────────

def get_access_token_remaining_seconds(jti_exp_timestamp: int) -> int:
    """
    计算 Access Token 的剩余有效秒数（用于设置黑名单 TTL）。
    exp_timestamp 为 JWT payload 中的 exp 字段（Unix 时间戳）。
    """
    now = datetime.now(timezone.utc).timestamp()
    remaining = int(jti_exp_timestamp - now)
    return max(remaining, 0)