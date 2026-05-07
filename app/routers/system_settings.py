r"""
文件位置: app/routers/system_settings.py
文件名称: system_settings.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.2.0
功能说明:
    系统设置路由。

管理端接口:
    /admin/api/system-settings/network
    /admin/api/system-settings/diagnostics
    /admin/api/system-settings/test-url

客户端接口:
    /api/client/network-config

设计边界:
    - 管理端接口需要 Admin Token。
    - 客户端 network-config 只返回安全公开字段。
    - 配置写操作接入 audit_log。
    - diagnostics / test-url 属于诊断动作，暂不写审计，避免日志噪音。

改进历史:
    V1.2.0 (2026-05-07): 网络设置保存接入 audit_log。
    V1.1.0 (2026-04-30): 初始系统设置路由。
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.redis_client import get_redis
from app.database import get_main_db
from app.models.main.models import Admin
from app.schemas.system_setting import (
    ClientNetworkConfigResponse,
    NetworkSettingsResponse,
    NetworkSettingsUpdateRequest,
    RuntimeDiagnosticsResponse,
    UrlTestRequest,
    UrlTestResponse,
)
from app.services.audit_service import create_audit_log
from app.services.system_setting_service import (
    get_client_network_config,
    get_network_settings,
    get_runtime_diagnostics,
    test_url_connectivity,
    update_network_settings,
)

admin_router = APIRouter()
client_router = APIRouter()


@admin_router.get("/network", summary="读取网络设置", response_model=NetworkSettingsResponse)
async def read_network_settings(
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> NetworkSettingsResponse:
    return await get_network_settings(db)


@admin_router.put("/network", summary="保存网络设置", response_model=NetworkSettingsResponse)
async def save_network_settings(
    body: NetworkSettingsUpdateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> NetworkSettingsResponse:
    result = await update_network_settings(
        db=db,
        body=body,
        admin_id=current_admin.id,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="system_settings.network.update",
        target_type="system_settings",
        target_id="network",
        summary="更新网络设置",
        metadata={
            "changed_fields": body.model_dump(exclude_unset=True),
            "public_base_url": result.public_base_url,
            "admin_base_url": result.admin_base_url,
            "update_base_url": result.update_base_url,
            "network_mode": result.network_mode,
            "heartbeat_interval_seconds": result.heartbeat_interval_seconds,
            "offline_threshold_seconds": result.offline_threshold_seconds,
        },
    )
    return result


@admin_router.get("/diagnostics", summary="系统运行诊断", response_model=RuntimeDiagnosticsResponse)
async def runtime_diagnostics(
    request: Request,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RuntimeDiagnosticsResponse:
    return await get_runtime_diagnostics(
        db=db,
        redis=redis,
        request=request,
    )


@admin_router.post("/test-url", summary="测试 URL 连通性", response_model=UrlTestResponse)
async def test_url(
    body: UrlTestRequest,
    _: Admin = Depends(get_current_admin),
) -> UrlTestResponse:
    return await test_url_connectivity(body)


@client_router.get("/network-config", summary="客户端网络配置", response_model=ClientNetworkConfigResponse)
async def client_network_config(
    db: AsyncSession = Depends(get_main_db),
) -> ClientNetworkConfigResponse:
    return await get_client_network_config(db)
