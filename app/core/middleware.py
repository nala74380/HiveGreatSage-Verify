r"""
文件位置: app/core/middleware.py
文件名称: middleware.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    平台级通用中间件。

当前包含:
    - RequestIdMiddleware: 为每个请求生成或透传 X-Request-ID。

设计边界:
    - request_id 只用于排障、日志、审计关联。
    - 不作为鉴权凭据。
    - 不信任客户端 request_id 作为安全事实，只作为追踪 ID。
"""

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import set_request_id

_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 64
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _normalize_request_id(value: str | None) -> str:
    """
    标准化 request_id。

    规则:
        - 允许客户端透传 X-Request-ID。
        - 只接受短安全字符集，避免日志注入。
        - 不合规则重新生成 UUID hex。
    """
    if value:
        candidate = value.strip()[:_MAX_REQUEST_ID_LENGTH]
        if _SAFE_REQUEST_ID_RE.match(candidate):
            return candidate
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求绑定 request_id，并写回响应头。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _normalize_request_id(request.headers.get(_REQUEST_ID_HEADER))
        set_request_id(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = request_id
        return response
