r"""
文件位置: app/routers/accounting.py
文件名称: accounting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心正式路由。

接口前缀:
    /admin/api/accounting

当前能力:
    - 账务总览
    - 点数账本
    - 代理钱包
    - 充值
    - 授信
    - 冻结授信
    - 解冻授信
    - 授权扣点快照
    - 删除返点记录

兼容说明:
    旧接口仍保留:
      /admin/api/balance-transactions
      /admin/api/agents/{agent_id}/balance
      /admin/api/agents/{agent_id}/recharge
      /admin/api/agents/{agent_id}/credit
      /admin/api/agents/{agent_id}/freeze
      /admin/api/agents/{agent_id}/unfreeze

    新前端应逐步改用:
      /admin/api/accounting/*
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.services.accounting_query_service import (
    get_accounting_overview,
    get_accounting_wallet_detail,
    list_accounting_wallets,
    list_authorization_charge_snapshots,
    list_refund_records,
)
from app.services.accounting_service import (
    credit_agent,
    freeze_credit,
    get_agent_balance,
    get_balance_transactions,
    recharge_agent,
    unfreeze_credit,
)

router = APIRouter()


class AccountingAmountRequest(BaseModel):
    amount: float = Field(..., gt=0, description="点数金额，必须大于 0")
    description: str | None = Field(default=None, description="备注 / 原因")


@router.get("/overview", summary="账务中心总览")
async def overview(
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_accounting_overview(db)


@router.get("/ledger", summary="点数账本")
async def ledger(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    entry_type: str | None = Query(default=None, description="账本类型：recharge/credit/freeze/unfreeze/consume/refund/adjust/reversal"),
    tx_type: str | None = Query(default=None, description="兼容旧字段，等同 entry_type"),
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
        tx_type=entry_type or tx_type,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
    )


@router.get("/wallets", summary="代理钱包列表")
async def wallets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    keyword: str | None = Query(default=None, description="代理用户名关键词"),
    status: str | None = Query(default=None, description="钱包状态 active/locked/closed"),
    risk_status: str | None = Query(default=None, description="风险状态 normal/watch/restricted/frozen"),
    agent_id: int | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await list_accounting_wallets(
        db=db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
        risk_status=risk_status,
        agent_id=agent_id,
    )


@router.get("/wallets/{agent_id}", summary="代理钱包详情")
async def wallet_detail(
    agent_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    wallet = await get_accounting_wallet_detail(agent_id, db)

    if wallet:
        return wallet

    # 如果尚无钱包，走写服务的 get_or_create 兼容逻辑创建空钱包并返回。
    return await get_agent_balance(agent_id, db)


@router.post("/agents/{agent_id}/recharge", summary="给代理充值点数")
async def recharge(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await recharge_agent(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )


@router.post("/agents/{agent_id}/credit", summary="给代理授信")
async def credit(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await credit_agent(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )


@router.post("/agents/{agent_id}/freeze", summary="冻结代理授信")
async def freeze(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await freeze_credit(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )


@router.post("/agents/{agent_id}/unfreeze", summary="解冻代理授信")
async def unfreeze(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await unfreeze_credit(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )


@router.get("/charges", summary="授权扣点快照")
async def charges(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    refund_status: str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await list_authorization_charge_snapshots(
        db=db,
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        refund_status=refund_status,
    )


@router.get("/refunds", summary="删除用户返点记录")
async def refunds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await list_refund_records(
        db=db,
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
    )