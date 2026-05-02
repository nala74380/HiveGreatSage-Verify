r"""
文件位置: app/core/timezone.py
名称: 时区工具
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能及相关说明:
    统一的时区工具模块，使用 Python 3.9+ 标准库 zoneinfo，无需额外依赖。

    数据库始终以 UTC 存储（DateTime(timezone=True)）。
    前端接收 ISO 8601 含时区字符串后，由 utils/format.js 统一转为 UTC+8 显示。
    后端此模块主要用于：
      1. 日志时间戳本地化
      2. 业务逻辑中比较"现在"与某个时间点（如 valid_until）

改进内容:
    V1.0.0 - 初始版本（使用 zoneinfo，无第三方依赖）
调试信息:
    已知问题: 无
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def get_tz() -> ZoneInfo:
    """返回配置的时区对象（默认 Asia/Shanghai）。"""
    return ZoneInfo(settings.TIMEZONE)


def now_local() -> datetime:
    """返回当前本地时区（UTC+8）的 aware datetime。"""
    return datetime.now(tz=get_tz())


def now_utc() -> datetime:
    """返回当前 UTC aware datetime，用于数据库写入。"""
    return datetime.now(tz=timezone.utc)


def to_local(dt: datetime | None) -> datetime | None:
    """
    将 UTC datetime 转换为配置时区（用于日志/调试输出）。
    API 响应的时区转换由前端负责。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_tz())


def utc_offset_str() -> str:
    """返回当前时区的 UTC 偏移字符串，如 '+08:00'。"""
    now = datetime.now(tz=get_tz())
    offset = now.utcoffset()
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    hours, remainder = divmod(abs(total_seconds), 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"
