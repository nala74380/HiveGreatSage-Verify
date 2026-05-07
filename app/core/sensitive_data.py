r"""
文件位置: app/core/sensitive_data.py
文件名称: sensitive_data.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    敏感字段脱敏与稳定哈希工具。

适用范围:
    - 设备指纹 device_fingerprint
    - IMSI
    - 审计日志 metadata 中需要可关联但不可明文扩散的字段

设计边界:
    - 本文件不负责数据库加密。
    - 本文件不改变业务校验逻辑。
    - hash_sensitive_value 使用 SECRET_KEY 做 HMAC key，便于同一环境内稳定关联。
    - SECRET_KEY 变更会导致新旧 hash 不一致，这是可接受的环境级边界。
"""

import hmac
import hashlib
from typing import Any

from app.config import settings


def mask_text(value: Any, *, head: int = 6, tail: int = 4, empty: str | None = None) -> str | None:
    """通用文本脱敏。"""
    if value is None:
        return empty

    text = str(value)
    if not text:
        return empty

    if len(text) <= head + tail:
        if len(text) <= 2:
            return "*" * len(text)
        return f"{text[:1]}***{text[-1:]}"

    return f"{text[:head]}***{text[-tail:]}"


def mask_device_fingerprint(value: Any) -> str | None:
    """设备指纹脱敏展示。"""
    return mask_text(value, head=8, tail=6)


def mask_imsi(value: Any) -> str | None:
    """IMSI 脱敏展示。"""
    return mask_text(value, head=5, tail=4)


def hash_sensitive_value(value: Any) -> str | None:
    """
    对敏感值生成稳定 HMAC-SHA256 哈希。

    用途:
        - 审计日志中做同值关联。
        - 前端列表中做非明文定位。

    注意:
        - 不用于密码存储。
        - 不用于鉴权。
    """
    if value is None:
        return None

    text = str(value)
    if not text:
        return None

    key = settings.SECRET_KEY.encode("utf-8")
    msg = text.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
