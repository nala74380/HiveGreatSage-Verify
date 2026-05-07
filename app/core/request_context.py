r"""
文件位置: app/core/request_context.py
文件名称: request_context.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    请求级上下文存储。

当前职责:
    - 保存当前请求 request_id。
    - 给路由、服务层、日志、审计链路提供统一读取入口。

边界:
    - 本文件只负责上下文变量。
    - request_id 的生成与响应头写入由 RequestIdMiddleware 负责。
"""

from contextvars import ContextVar

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    """设置当前请求 request_id。"""
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """读取当前请求 request_id。没有请求上下文时返回 None。"""
    return _request_id_var.get()
