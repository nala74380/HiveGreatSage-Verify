r"""
文件位置: app/services/audit_service.py
文件名称: audit_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.1.0
功能说明:
    平台通用审计日志服务。

设计目标:
    - 业务路由不直接操作 AuditLog ORM。
    - 统一写入 request_id。
    - 统一过滤 metadata 中的敏感字段。
    - 审计日志写入失败不应吞掉主业务异常，也不应阻止主业务正常返回。

边界:
    - 本服务负责创建 AuditLog 对象并 flush。
    - 事务 commit 仍由调用方控制。

改进历史:
    V1.1.0 (2026-05-07): 敏感字段过滤从精确匹配增强为名称片段 / 后缀匹配。
    V1.0.0 (2026-05-07): 初始版本。
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.models.main.audit import AuditLog

ActorType = Literal["admin", "agent", "user", "system"]

_SENSITIVE_EXACT_KEYS = {
    "authorization",
    "file_data",
    "file_content",
}

_SENSITIVE_KEY_PARTS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "credentials",
}

_SENSITIVE_KEY_SUFFIXES = {
    "_key",
    "_secret",
    "_token",
    "_password",
    "_hash",
}


def _is_sensitive_key(key: str) -> bool:
    """判断 metadata key 是否属于敏感字段。"""
    normalized = key.strip().lower().replace("-", "_")
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True

    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        return True

    return any(normalized.endswith(suffix) for suffix in _SENSITIVE_KEY_SUFFIXES)


def _sanitize_metadata(value: Any) -> Any:
    """递归清理敏感字段，避免审计日志保存明文密码 / Token / 文件内容。"""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                clean[key_text] = "<redacted>"
            else:
                clean[key_text] = _sanitize_metadata(item)
        return clean

    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]

    if isinstance(value, tuple):
        return [_sanitize_metadata(item) for item in value]

    return value


async def create_audit_log(
    *,
    db: AsyncSession,
    actor_type: ActorType,
    actor_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """
    创建审计日志。

    注意:
        - 不 commit，由调用方事务统一控制。
        - target_id 统一转为字符串，兼容 int / UUID。
        - metadata 会递归脱敏。
    """
    audit = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        summary=summary,
        metadata_json=_sanitize_metadata(metadata) if metadata is not None else None,
        request_id=request_id or get_request_id(),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit)
    await db.flush()
    return audit
