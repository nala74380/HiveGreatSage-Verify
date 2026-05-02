"""
文件位置: app/routers/pricing.py
名称: 项目定价路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-03
版本: V2.0.0
功能说明:
    管理员专用项目定价接口。

    旧版 balance_admin.py 已删除。定价功能独立为 pricing.py。
    其余旧 balance_admin 端点（recharge/credit/freeze/unfreeze/balance/transactions）
    已在 accounting.py 中重新实现。

接口:
    GET    /admin/api/prices/{project_id}            获取项目各级别定价
    PUT    /admin/api/prices/{project_id}/{user_level}  设置/更新单价
    DELETE /admin/api/prices/{project_id}/{user_level}  删除单价

改进历史:
    V2.0.0 (2026-05-03) - 从 balance_admin.py 拆出，去除已迁移的旧端点
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.services.accounting_service import (
    delete_project_price,
    get_project_prices,
    set_project_price,
)

router = APIRouter()


class SetPriceRequest(BaseModel):
    points_per_device: float = Field(..., ge=0, description="每台设备消耗点数")


@router.get("/prices/{project_id}", summary="获取项目各级别定价")
async def get_prices(
    project_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    return await get_project_prices(project_id, db)


@router.put("/prices/{project_id}/{user_level}", summary="设置/更新单价")
async def set_price(
    project_id: int,
    user_level: str,
    body: SetPriceRequest,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await set_project_price(project_id, user_level, body.points_per_device, db)


@router.delete("/prices/{project_id}/{user_level}", status_code=204, summary="删除单价")
async def delete_price(
    project_id: int,
    user_level: str,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    await delete_project_price(project_id, user_level, db)
