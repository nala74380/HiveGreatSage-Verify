r"""
文件位置: app/routers/balance.py
名称: 点数余额与项目定价路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.0.0
功能说明:
    项目定价管理（Admin）：
      GET    /admin/api/prices/{project_id}                    获取项目各级别定价
      PUT    /admin/api/prices/{project_id}/{user_level}       设置/更新单价
      DELETE /admin/api/prices/{project_id}/{user_level}       删除单价

    公开定价目录（代理查看）：
      GET    /api/prices/catalog                               全项目定价目录

    代理余额管理（Admin）：
      GET    /admin/api/agents/{agent_id}/balance              查询余额
      POST   /admin/api/agents/{agent_id}/recharge             充值
      POST   /admin/api/agents/{agent_id}/credit               授信
      POST   /admin/api/agents/{agent_id}/freeze               冻结授信
      POST   /admin/api/agents/{agent_id}/unfreeze             解冻授信
      GET    /admin/api/agents/{agent_id}/transactions         流水记录

    代理自查（Agent Token）：
      GET    /api/agents/my/balance                            查询自己余额
      GET    /api/agents/my/transactions                       查询自己流水
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_agent
from app.database import get_main_db
from app.models.main.models import Admin, Agent
from app.services.balance_service import (
    credit_agent,
    delete_project_price,
    freeze_credit,
    get_agent_balance,
    get_agents_with_balance_and_projects,
    get_all_projects_with_prices,
    get_balance_transactions,
    get_project_prices,
    recharge_agent,
    set_project_price,
    unfreeze_credit,
)

router = APIRouter()


# ── Pydantic 请求体 ───────────────────────────────────────────

class SetPriceRequest(BaseModel):
    points_per_device: float = Field(..., ge=0, description="每台设备消耗点数")


class RechargeRequest(BaseModel):
    amount:      float        = Field(..., gt=0, description="充值点数")
    description: str | None  = Field(default=None, description="备注")


class CreditRequest(BaseModel):
    amount:      float        = Field(..., gt=0, description="授信点数")
    description: str | None  = Field(default=None, description="备注")


class FreezeRequest(BaseModel):
    amount:      float        = Field(..., gt=0, description="冻结点数")
    description: str | None  = Field(default=None, description="备注")


class UnfreezeRequest(BaseModel):
    amount:      float        = Field(..., gt=0, description="解冻点数")
    description: str | None  = Field(default=None, description="备注")


# ── 项目定价（Admin）─────────────────────────────────────────

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


# ── 定价目录（公开给代理）────────────────────────────────────

@router.get("/catalog", summary="全项目定价目录（代理查看）", tags=["定价目录"])
async def price_catalog(
    _: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    """代理查看所有项目的定价，并可申请授权。"""
    return await get_all_projects_with_prices(db)


# ── 代理余额管理（Admin）─────────────────────────────────────

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
    """
    线下充值后，管理员在后台录入点数。
    充值点数优先于授信点数使用。
    """
    return await recharge_agent(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/credit", summary="给代理授信")
async def credit(
    agent_id: int,
    body: CreditRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """授信点数，可随时冻结（用于风控）。"""
    return await credit_agent(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/freeze", summary="冻结授信点数")
async def freeze(
    agent_id: int,
    body: FreezeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """冻结代理的授信点数（不能超过可用授信余额）。"""
    return await freeze_credit(agent_id, body.amount, body.description, current_admin.id, db)


@router.post("/agents/{agent_id}/unfreeze", summary="解冻授信点数")
async def unfreeze(
    agent_id: int,
    body: UnfreezeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await unfreeze_credit(agent_id, body.amount, body.description, current_admin.id, db)


@router.get("/agents/{agent_id}/transactions", summary="查询代理流水记录")
async def transactions(
    agent_id: int,
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tx_type:   str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(agent_id, db, page, page_size, tx_type)


# ── 代理自查（Agent Token）──────────────────────────────────

@router.get("/my/balance", summary="代理查询自己余额")
async def my_balance(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_agent_balance(current_agent.id, db)


@router.get("/my/transactions", summary="代理查询自己流水")
async def my_transactions(
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(current_agent.id, db, page, page_size)


# ── 增强代理列表（含余额+项目，替代旧接口）─────────────────────

@router.get("/agents-full", summary="代理列表（含余额和授权项目）")
async def agents_full_list(
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status:    str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """代理管理页面专用接口，一次返回余额和已授权项目信息，避免 N+1。"""
    return await get_agents_with_balance_and_projects(db, page, page_size, status)
