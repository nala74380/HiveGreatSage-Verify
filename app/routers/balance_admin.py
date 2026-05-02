r"""
文件位置: app/routers/balance_admin.py
名称: 管理端点数余额与项目定价路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.1.0
功能说明:
    管理员专用点数与定价接口。只挂载到 /admin/api。

新增能力:
    GET /admin/api/balance-transactions
        管理员全局点数流水页面使用。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.services.accounting_service import (
    credit_agent,
    delete_project_price,
    freeze_credit,
    get_agent_balance,
    get_agents_with_balance_and_projects,
    get_balance_transactions,
    get_project_prices,
    recharge_agent,
    set_project_price,
    unfreeze_credit,
)

router = APIRouter()


class SetPriceRequest(BaseModel):
    points_per_device: float = Field(..., ge=0, description="每台设备消耗点数")


class RechargeRequest(BaseModel):
    amount: float = Field(..., gt=0, description="充值点数")
    description: str | None = Field(default=None, description="备注")


class CreditRequest(BaseModel):
    amount: float = Field(..., gt=0, description="授信点数")
    description: str | None = Field(default=None, description="备注")


class FreezeRequest(BaseModel):
    amount: float = Field(..., gt=0, description="冻结点数")
    description: str | None = Field(default=None, description="备注")


class UnfreezeRequest(BaseModel):
    amount: float = Field(..., gt=0, description="解冻点数")
    description: str | None = Field(default=None, description="备注")


# ── 管理员全局流水 ───────────────────────────────────────────

@router.get("/balance-transactions", summary="管理员全局点数流水")
async def global_balance_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tx_type: str | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    related_user_id: int | None = Query(default=None),
    related_project_id: int | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(
        agent_id=agent_id,
        db=db,
        page=page,
        page_size=page_size,
        tx_type=tx_type,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
    )


# ── 项目定价 ────────────────────────────────────────────────

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


# ── 代理余额管理 ────────────────────────────────────────────

@router.get("/agents/{agent_id}/balance", summary="查询代理余额")
async def get_balance(
    agent_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_agent_balance(agent_id, db)


@router.post("/agents/{agent_id}/recharge", summary="给代理充值点数")
async def recharge(
    agent_id: int,
    body: RechargeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await recharge_agent(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/credit", summary="给代理授信")
async def credit(
    agent_id: int,
    body: CreditRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await credit_agent(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/freeze", summary="冻结授信点数")
async def freeze(
    agent_id: int,
    body: FreezeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await freeze_credit(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/unfreeze", summary="解冻授信点数")
async def unfreeze(
    agent_id: int,
    body: UnfreezeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await unfreeze_credit(agent_id, body.amount, body.description, current_admin.id, db)


@router.get("/agents/{agent_id}/transactions", summary="查询某代理流水记录")
async def transactions(
    agent_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tx_type: str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(agent_id, db, page, page_size, tx_type)


@router.get("/agents-full", summary="代理列表（含余额和授权项目）")
async def agents_full_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_agents_with_balance_and_projects(db, page, page_size, status)
