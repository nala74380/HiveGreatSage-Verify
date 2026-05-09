r"""
文件位置: app/core/security.py
文件名称: security.py
作者: HiveGreatSage Dev
日期/时间: 2026-05-07
版本: V1.1.0
功能说明:
    安全模块，提供两类功能：
      1. 密码哈希：使用 bcrypt，verify_password / hash_password
      2. JWT 管理：
         - User Access Token（含 sub/authorization_level/project_code/jti）
         - User Refresh Token（不透明字符串，存 Redis）
         - Admin Token（type=admin，含 sub/jti）
         - Agent Token（type=agent，含 sub/jti）

    所有 JWT 都必须包含 jti，便于写入 Redis 黑名单实现服务端吊销。
    所有有效期从 config.settings 读取，不硬编码。

改进历史:
    V1.1.0 (2026-05-07) - Admin / Agent Token 增加 jti，接入统一黑名单吊销基础。
    V1.0.2 - 新增 Admin/Agent Token 签发/校验函数。
    V1.0.0 - 初始版本。
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


# ── User Access Token ─────────────────────────────────────────

def create_access_token(
    user_id: int,
    authorization_level: str,
    game_project_code: str,
    token_version: int = 0,
) -> tuple[str, str]:
    """
    签发 User Access Token（JWT，HS256）。

    Payload 字段：
        sub                 : str(user_id)
        authorization_level : Authorization.user_level
        project_code        : game_project.code_name
        jti                 : UUID v4，用于黑名单校验
        iat                 : 签发时间
        exp                 : 过期时间
        type                : access

    返回：
        (token_string, jti) — jti 需要与 Refresh Token 关联存入 Redis。
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "authorization_level": authorization_level,
        "project_code": game_project_code,
        "token_version": int(token_version),
        "jti": jti,
        "iat": now,
        "exp": expire,
        "type": "access",
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码并验证 User Access Token。

    返回 payload 字典（已验证签名和有效期）。
    失败时抛出 JWTError（由调用方转换为 HTTP 401）。
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    if payload.get("type") != "access":
        raise JWTError("Invalid token type")

    if not payload.get("jti"):
        raise JWTError("Missing token jti")

    return payload


# ── User Refresh Token ────────────────────────────────────────

def create_refresh_token() -> str:
    """
    生成不透明的 Refresh Token（URL-safe 随机字符串，48字节 = 64字符）。
    RT 本身不携带信息，所有状态存在 Redis 中（Key: refresh:{user_id}:{jti}）。
    """
    return secrets.token_urlsafe(48)


def get_refresh_token_ttl_seconds() -> int:
    """返回 Refresh Token 的 TTL（秒），从配置读取。"""
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


# ── 通用工具函数 ──────────────────────────────────────────────

def get_access_token_remaining_seconds(exp_timestamp: int) -> int:
    """
    计算 JWT 剩余有效秒数（用于设置黑名单 TTL）。

    exp_timestamp 为 JWT payload 中的 exp 字段（Unix 时间戳）。
    """
    now = datetime.now(timezone.utc).timestamp()
    remaining = int(exp_timestamp - now)
    return max(remaining, 0)


def _new_jti() -> str:
    """生成 JWT ID。"""
    return str(uuid.uuid4())


# ── Admin Token ───────────────────────────────────────────────

def create_admin_token(admin_id: int) -> str:
    """
    签发管理员 Token（type=admin）。

    与用户 Access Token 区分：
      - 不含 project_code。
      - 含 jti，可接入 Redis 黑名单。
      - 当前没有 refresh_token，过期后重新登录。
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ADMIN_TOKEN_EXPIRE_HOURS)
    payload: dict[str, Any] = {
        "sub": str(admin_id),
        "type": "admin",
        "jti": _new_jti(),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_admin_token(token: str) -> dict[str, Any]:
    """
    解码并验证 Admin Token。
    失败时抛出 JWTError（由调用方转换为 HTTP 401）。
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "admin":
        raise JWTError("Invalid token type: expected admin")
    if not payload.get("jti"):
        raise JWTError("Missing token jti")
    return payload


# ── Agent Token ───────────────────────────────────────────────

def create_agent_token(agent_id: int) -> str:
    """
    签发代理 Token（type=agent）。

    当前没有 refresh_token，过期后重新登录。
    Token 含 jti，可接入 Redis 黑名单。
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.AGENT_TOKEN_EXPIRE_HOURS)
    payload: dict[str, Any] = {
        "sub": str(agent_id),
        "type": "agent",
        "jti": _new_jti(),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_agent_token(token: str) -> dict[str, Any]:
    """
    解码并验证 Agent Token。
    失败时抛出 JWTError（由调用方转换为 HTTP 401）。
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "agent":
        raise JWTError("Invalid token type: expected agent")
    if not payload.get("jti"):
        raise JWTError("Missing token jti")
    return payload
