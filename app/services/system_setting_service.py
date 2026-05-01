r"""
文件位置: app/services/system_setting_service.py
文件名称: system_setting_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    系统设置服务层。

当前能力:
    - 读取网络设置
    - 保存网络设置
    - 初始化默认网络设置
    - 生成客户端网络配置
    - 简单运行诊断

设计边界:
    - 本服务只管理运行期业务配置。
    - 不管理 DATABASE_URL / REDIS_URL / SECRET_KEY / JWT 密钥等部署级配置。
"""

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.system_setting import SystemSetting
from app.schemas.system_setting import (
    ClientNetworkConfigResponse,
    NetworkSettingsResponse,
    NetworkSettingsUpdateRequest,
    RuntimeDiagnosticsResponse,
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
    settings = await get_network_settings(db)

    primary_api_url = (
        settings.pc_client_api_url
        or settings.public_api_base_url
        or settings.relay_url
    )

    return ClientNetworkConfigResponse(
        config_version=settings.config_version,
        deployment_mode=settings.deployment_mode,
        primary_api_url=primary_api_url,
        pc_client_api_url=settings.pc_client_api_url or primary_api_url,
        android_client_api_url=settings.android_client_api_url or primary_api_url,
        backup_api_urls=settings.backup_api_urls,
        timeout_seconds=settings.client_timeout_seconds,
        retry_count=settings.client_retry_count,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        relay_enabled=settings.relay_enabled,
        relay_mode=settings.relay_mode,
        relay_url=settings.relay_url,
    )


async def get_runtime_diagnostics(db: AsyncSession) -> RuntimeDiagnosticsResponse:
    settings = await get_network_settings(db)

    return RuntimeDiagnosticsResponse(
        status="ok",
        server_time=datetime.now(timezone.utc).isoformat(),
        network_settings_loaded=True,
        deployment_mode=settings.deployment_mode,
        public_api_base_url=settings.public_api_base_url,
        relay_enabled=settings.relay_enabled,
        relay_mode=settings.relay_mode,
        relay_url=settings.relay_url,
    )