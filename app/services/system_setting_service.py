r"""
文件位置: app/services/system_setting_service.py
文件名称: system_setting_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-01
版本: V1.2.0
功能说明:
    系统设置服务层。

当前能力:
    - 读取网络设置
    - 保存网络设置
    - 初始化默认网络设置
    - 生成客户端网络配置
    - URL 连通性测试
    - 运行诊断

本版改进:
    V1.2.0:
        - 增加 D 模式连接策略字段。
        - 默认 route_strategy = relay_only。
        - 默认 direct_enabled = false。
        - 客户端 network-config 下发 route_strategy / direct_* 字段。

设计边界:
    - 本服务只管理运行期业务配置。
    - 不管理 DATABASE_URL / REDIS_URL / SECRET_KEY / JWT 密钥等部署级配置。
    - D 模式当前默认用于家庭无公网 IP 场景，因此不默认开启直连。
"""

import asyncio
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.main.system_setting import SystemSetting
from app.schemas.system_setting import (
    ClientNetworkConfigResponse,
    NetworkSettingsResponse,
    NetworkSettingsUpdateRequest,
    RuntimeDiagnosticsResponse,
    UrlTestRequest,
    UrlTestResponse,
)


NETWORK_DEFAULTS: dict[str, tuple[Any, str, str]] = {
    "deployment_mode": ("relay_tunnel", "string", "当前主部署模式"),

    "public_api_base_url": ("", "string", "对外 API 公网访问地址"),
    "public_admin_base_url": ("", "string", "管理后台公网访问地址"),
    "public_update_base_url": ("", "string", "热更新资源公网访问地址"),
    "health_check_url": ("", "string", "公网健康检查地址"),

    "reverse_proxy_enabled": (True, "bool", "是否启用反向代理"),
    "reverse_proxy_url": ("", "string", "公网反向代理地址"),
    "force_https": (True, "bool", "是否要求 HTTPS"),
    "real_ip_header": ("X-Forwarded-For", "string", "真实客户端 IP Header"),
    "trusted_proxy_enabled": (False, "bool", "是否启用可信代理 IP 校验"),
    "trusted_proxy_ips": ([], "json", "可信代理 IP 列表"),

    "relay_enabled": (True, "bool", "是否启用公网中转/隧道"),
    "relay_mode": ("frp", "string", "中转/隧道模式"),
    "relay_url": ("", "string", "公网中转访问地址"),
    "relay_health_url": ("", "string", "中转健康检查地址"),
    "home_node_id": ("home-main-001", "string", "家庭服务器节点 ID"),
    "home_node_name": ("家庭主节点", "string", "家庭服务器节点名称"),
    "home_local_verify_url": ("http://127.0.0.1:8000", "string", "家庭本地 Verify 地址"),

    # D 模式连接策略。
    # 当前前提：家庭无公网 IP，因此默认 relay_only。
    "route_strategy": ("relay_only", "string", "D 模式路由策略"),
    "direct_enabled": (False, "bool", "是否启用直连候选地址"),
    "direct_candidate_urls": ([], "json", "直连候选 API 地址列表"),
    "direct_health_url": ("", "string", "直连健康检查地址"),
    "direct_min_success_count": (2, "int", "直连切换前最小连续成功次数"),
    "direct_failback_threshold": (2, "int", "直连失败回退中转的阈值"),
    "relay_keepalive_after_direct": (True, "bool", "直连后是否保持中转作为控制面"),
    "preferred_route": ("relay", "string", "优先线路：relay/direct/auto"),

    "client_config_enabled": (True, "bool", "是否启用客户端网络配置下发"),
    "config_version": (1, "int", "客户端网络配置版本号"),
    "pc_client_api_url": ("", "string", "PC 中控推荐 API 地址"),
    "android_client_api_url": ("", "string", "安卓脚本推荐 API 地址"),
    "backup_api_urls": ([], "json", "备用 API 地址列表"),
    "client_timeout_seconds": (15, "int", "客户端请求超时时间"),
    "client_retry_count": (3, "int", "客户端请求重试次数"),
    "heartbeat_interval_seconds": (30, "int", "客户端心跳间隔"),
    "allow_client_config_pull": (True, "bool", "是否允许客户端拉取远程配置"),
    "allow_client_auto_failover": (True, "bool", "是否允许客户端自动切换备用地址"),
}


def _serialize_value(value: Any, value_type: str) -> str:
    if value_type == "json":
        return json.dumps(value, ensure_ascii=False)

    if value_type == "bool":
        return "true" if bool(value) else "false"

    return str(value)


def _parse_value(raw: str | None, value_type: str, default: Any) -> Any:
    if raw is None:
        return default

    if value_type == "int":
        try:
            return int(raw)
        except Exception:
            return default

    if value_type == "float":
        try:
            return float(raw)
        except Exception:
            return default

    if value_type == "bool":
        return str(raw).lower() in {"true", "1", "yes", "on"}

    if value_type == "json":
        try:
            return json.loads(raw)
        except Exception:
            return default

    return raw


async def ensure_network_settings(db: AsyncSession) -> None:
    """确保 network 默认配置存在。"""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.category == "network")
    )
    existing = {
        item.setting_key: item
        for item in result.scalars().all()
    }

    for key, (default_value, value_type, description) in NETWORK_DEFAULTS.items():
        if key in existing:
            continue

        item = SystemSetting(
            category="network",
            setting_key=key,
            setting_value=_serialize_value(default_value, value_type),
            value_type=value_type,
            is_editable=True,
            is_secret=False,
            description=description,
        )
        db.add(item)

    await db.flush()


async def get_network_settings(db: AsyncSession) -> NetworkSettingsResponse:
    await ensure_network_settings(db)

    result = await db.execute(
        select(SystemSetting).where(SystemSetting.category == "network")
    )
    rows = result.scalars().all()

    raw_map = {
        item.setting_key: item
        for item in rows
    }

    data: dict[str, Any] = {}

    latest_updated_at = None
    latest_admin_id = None

    for key, (default_value, value_type, _description) in NETWORK_DEFAULTS.items():
        item = raw_map.get(key)
        data[key] = _parse_value(
            item.setting_value if item else None,
            item.value_type if item else value_type,
            default_value,
        )

        if item and item.updated_at:
            if latest_updated_at is None or item.updated_at > latest_updated_at:
                latest_updated_at = item.updated_at
                latest_admin_id = item.updated_by_admin_id

    data["updated_at"] = latest_updated_at.isoformat() if latest_updated_at else None
    data["updated_by_admin_id"] = latest_admin_id

    return NetworkSettingsResponse(**data)


async def update_network_settings(
    *,
    db: AsyncSession,
    body: NetworkSettingsUpdateRequest,
    admin_id: int,
) -> NetworkSettingsResponse:
    """
    保存网络设置。

    规则:
      - 只更新 NETWORK_DEFAULTS 中声明的字段。
      - 每次保存自动 config_version + 1。
      - 不立即改变当前后台浏览器请求地址。
    """
    await ensure_network_settings(db)

    result = await db.execute(
        select(SystemSetting).where(SystemSetting.category == "network")
    )
    existing = {
        item.setting_key: item
        for item in result.scalars().all()
    }

    payload = body.model_dump()

    current_version = int(payload.get("config_version") or 1)
    payload["config_version"] = current_version + 1

    for key, (default_value, value_type, description) in NETWORK_DEFAULTS.items():
        value = payload.get(key, default_value)
        setting_value = _serialize_value(value, value_type)

        item = existing.get(key)

        if not item:
            item = SystemSetting(
                category="network",
                setting_key=key,
                value_type=value_type,
                is_editable=True,
                is_secret=False,
                description=description,
            )
            db.add(item)

        item.setting_value = setting_value
        item.value_type = value_type
        item.description = description
        item.updated_by_admin_id = admin_id

    await db.flush()

    return await get_network_settings(db)


async def get_client_network_config(db: AsyncSession) -> ClientNetworkConfigResponse:
    """
    生成 PC 中控 / 安卓脚本可读取的安全网络配置。

    不返回:
      - home_local_verify_url
      - trusted_proxy_ips
      - origin_server_url
      - 数据库 / Redis / 密钥
    """
    network = await get_network_settings(db)

    primary_api_url = (
        network.pc_client_api_url
        or network.public_api_base_url
        or network.relay_url
    )

    return ClientNetworkConfigResponse(
        config_version=network.config_version,
        deployment_mode=network.deployment_mode,

        primary_api_url=primary_api_url,
        pc_client_api_url=network.pc_client_api_url or primary_api_url,
        android_client_api_url=network.android_client_api_url or primary_api_url,
        backup_api_urls=network.backup_api_urls,

        timeout_seconds=network.client_timeout_seconds,
        retry_count=network.client_retry_count,
        heartbeat_interval_seconds=network.heartbeat_interval_seconds,

        relay_enabled=network.relay_enabled,
        relay_mode=network.relay_mode,
        relay_url=network.relay_url,

        route_strategy=network.route_strategy,
        direct_enabled=network.direct_enabled,
        direct_candidate_urls=network.direct_candidate_urls,
        direct_health_url=network.direct_health_url,
        direct_min_success_count=network.direct_min_success_count,
        direct_failback_threshold=network.direct_failback_threshold,
        relay_keepalive_after_direct=network.relay_keepalive_after_direct,
        preferred_route=network.preferred_route,
    )


def _test_url_sync(
    *,
    target_name: str,
    url: str,
    timeout_seconds: int,
) -> UrlTestResponse:
    checked_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    request = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "User-Agent": "HiveGreatSage-Verify-Network-Diagnostics/1.0",
            "Accept": "*/*",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            status_code = int(response.status)

            return UrlTestResponse(
                target_name=target_name,
                url=url,
                success=200 <= status_code < 400,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                final_url=response.geturl(),
                error=None,
                checked_at=checked_at,
            )

    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status_code = int(exc.code)

        return UrlTestResponse(
            target_name=target_name,
            url=url,
            success=False,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            final_url=exc.geturl(),
            error=str(exc.reason),
            checked_at=checked_at,
        )

    except urllib.error.URLError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return UrlTestResponse(
            target_name=target_name,
            url=url,
            success=False,
            status_code=None,
            elapsed_ms=elapsed_ms,
            final_url=None,
            error=str(exc.reason),
            checked_at=checked_at,
        )

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return UrlTestResponse(
            target_name=target_name,
            url=url,
            success=False,
            status_code=None,
            elapsed_ms=elapsed_ms,
            final_url=None,
            error=str(exc),
            checked_at=checked_at,
        )


async def test_url_connectivity(body: UrlTestRequest) -> UrlTestResponse:
    """
    测试 URL 连通性。

    说明:
      - 使用标准库 urllib，避免引入新依赖。
      - 在后台线程执行，避免阻塞事件循环。
      - 只做连通性诊断，不写入配置。
    """
    return await asyncio.to_thread(
        _test_url_sync,
        target_name=body.target_name,
        url=body.url,
        timeout_seconds=body.timeout_seconds,
    )


async def _check_database(db: AsyncSession) -> tuple[str, str | None]:
    try:
        await db.execute(text("SELECT 1"))
        return "ok", None
    except Exception as exc:
        return "error", str(exc)


async def _check_redis(redis: aioredis.Redis) -> tuple[str, str | None]:
    try:
        await redis.ping()
        return "ok", None
    except Exception as exc:
        return "error", str(exc)


def _selected_real_ip_value(
    *,
    real_ip_header: str,
    x_forwarded_for: str | None,
    x_real_ip: str | None,
    cf_connecting_ip: str | None,
    request_remote_addr: str | None,
) -> str | None:
    if real_ip_header == "X-Forwarded-For":
        return x_forwarded_for or request_remote_addr

    if real_ip_header == "X-Real-IP":
        return x_real_ip or request_remote_addr

    if real_ip_header == "CF-Connecting-IP":
        return cf_connecting_ip or request_remote_addr

    return request_remote_addr


async def get_runtime_diagnostics(
    *,
    db: AsyncSession,
    redis: aioredis.Redis,
    request: Request,
) -> RuntimeDiagnosticsResponse:
    network = await get_network_settings(db)

    database_status, database_error = await _check_database(db)
    redis_status, redis_error = await _check_redis(redis)

    request_remote_addr = request.client.host if request.client else None
    x_forwarded_for = request.headers.get("x-forwarded-for")
    x_real_ip = request.headers.get("x-real-ip")
    cf_connecting_ip = request.headers.get("cf-connecting-ip")

    selected_ip = _selected_real_ip_value(
        real_ip_header=network.real_ip_header,
        x_forwarded_for=x_forwarded_for,
        x_real_ip=x_real_ip,
        cf_connecting_ip=cf_connecting_ip,
        request_remote_addr=request_remote_addr,
    )

    global_status = "ok"
    if database_status != "ok" or redis_status != "ok":
        global_status = "degraded"

    return RuntimeDiagnosticsResponse(
        status=global_status,
        server_time=datetime.now(timezone.utc).isoformat(),
        environment=settings.ENVIRONMENT,
        backend_timezone=settings.TIMEZONE,

        database_status=database_status,
        database_error=database_error,
        redis_status=redis_status,
        redis_error=redis_error,

        network_settings_loaded=True,
        deployment_mode=network.deployment_mode,

        public_api_base_url=network.public_api_base_url,
        public_admin_base_url=network.public_admin_base_url,
        public_update_base_url=network.public_update_base_url,

        relay_enabled=network.relay_enabled,
        relay_mode=network.relay_mode,
        relay_url=network.relay_url,
        relay_health_url=network.relay_health_url,

        route_strategy=network.route_strategy,
        direct_enabled=network.direct_enabled,
        direct_candidate_urls=network.direct_candidate_urls,
        direct_health_url=network.direct_health_url,
        preferred_route=network.preferred_route,

        reverse_proxy_enabled=network.reverse_proxy_enabled,
        reverse_proxy_url=network.reverse_proxy_url,
        real_ip_header=network.real_ip_header,
        trusted_proxy_enabled=network.trusted_proxy_enabled,

        request_remote_addr=request_remote_addr,
        x_forwarded_for=x_forwarded_for,
        x_real_ip=x_real_ip,
        cf_connecting_ip=cf_connecting_ip,
        selected_real_ip_value=selected_ip,
    )