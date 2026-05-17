r"""
文件位置: app/core/sensitive_data.py
文件名称: sensitive_data.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-18
版本: V1.1.0
功能说明:
    设备标识相关文本工具。

设计边界:
    - 本文件只保留通用文本处理函数。
    - 不再承担设备标识脱敏或摘要生成职责。
"""

from typing import Any


def normalize_text(value: Any, empty: str | None = None) -> str | None:
    """将任意值规范为字符串；None 或空字符串时返回 empty。"""
    if value is None:
        return empty

    text = str(value).strip()
    if not text:
        return empty
    return text
