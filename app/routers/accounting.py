r"""
文件位置: app/routers/accounting.py
文件名称: accounting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-08
版本: V1.3.1
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
    - 冻结 / 解冻
    - 授权扣点快照
    - 删除返点记录
    - 初始化开发期账务基线
    - 运行对账
    - 对账批次列表
    - 对账批次详情

改进历史:
    V1.3.1 (2026-05-08): agents-full 回填 authorized_projects[].user_count。
    V1.3.0 (2026-05-07): 对账初始化、运行对账接入 audit_log。
    V1.2.0 (2026-05-07): 充值、授信、冻结、解冻接入 audit_log。
    V1.1.0 (2026-04-30): 账务中心正式路由。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin, Authorization, User
from app.services.accounting_query_service import (
    get_accounting_overview,
    get_accounting_wallet_detail,
    list_accounting_wallets,
    list_authorization_charge_snapshots,
    list_refund_records,
)
from app.services.accounting_reconciliation_service import (
    get_reconciliation_run_detail,
    initialize_reconciliation_baseline,
    list_reconciliation_runs,
    run_reconciliation,
)
from app.services.accounting_service import (
    credit_agent,
    freeze_credit,
    get_agent_balance,
    get_balance_transactions,
    recharge_agent,
    unfreeze_credit,
)
from app.services.audit_service import create_audit_log

router = APIRouter()


class AccountingAmountRequest(BaseModel):
    amount: float = Field(..., gt=0, description="点数金额，必须大于 0")
    description: str | None = Field(default=None, description="备注 / 原因")


def _audit_wallet_metadata(
    *,
    agent_id: int,
    amount: float,
    description: str | None,
    wallet: dict,
) -> dict:
    """生成账务写操作审计元数据。"""
    return {
        "agent_id": agent_id,
        "amount": amount,
        "description": description,
        "charged_balance": wallet.get("charged_balance"),
        "credit_balance": wallet.get("credit_balance"),
        "frozen_credit": wallet.get("frozen_credit"),
        "available_credit": wallet.get("available_credit"),
        "available_total": wallet.get("available_total"),
        "wallet_status": wallet.get("status"),
        "risk_status": wallet.get("risk_status"),
    }


def _audit_reconciliation_metadata(
    *,
    agent_id: int | None,
    result: dict,
) -> dict:
    """生成对账操作审计元数据。"""
    return {
        "agent_id": agent_id,
        "scope": "agent" if agent_id is not None else "all",
        "result": result,
    }


async def _fill_agent_project_user_counts(
    *,
    db: AsyncSession,
    result: dict,
) -> dict:
    """
    回填代理列表中每个已授权项目的直属授权用户数。

    统计口径:
      - 只统计 User.created_by_agent_id 等于该代理 ID 的直属用户。
      - 只统计未软删除用户。
      - 只统计 Authorization.status == active 的项目授权。
      - 维度为 agent_id + game_project_id。
    """
    agents = result.get("agents") or []
    agent_ids = [int(item["id"]) for item in agents if item.get("id") is not None]
    if not agent_ids:
        return result

    count_result = await db.execute(
        select(
            User.created_by_agent_id,
            Authorization.game_project_id,
            func.count(Authorization.id),
        )
        .join(Authorization, Authorization.user_id == User.id)
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
            Authorization.status == "active",
        )
        .group_by(User.created_by_agent_id, Authorization.game_project_id)
    )

    count_map: dict[tuple[int, int], int] = {
        (int(agent_id), int(project_id)): int(count)
        for agent_id, project_id, count in count_result.all()
        if agent_id is not None and project_id is not None
    }

    for agent in agents:
        agent_id = agent.get("id")
        if agent_id is None:
            continue

        projects = agent.get("authorized_projects")
        if projects is None:
            projects = agent.get("project_auths") or []
            agent["authorized_projects"] = projects

        for project in projects:
            project_id = (
                project.get("project_id")
                or project.get("id")
                or project.get("game_project_id")
            )
            if project_id is None:
                project["user_count"] = 0
                continue
            project["user_count"] = count_map.get((int(agent_id), int(project_id)), 0)

    return result


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


@router.get("/agents-full", summary="代理列表含余额与项目授权")
async def agents_full(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """代理列表（含余额与授权项目），前端 AgentList.vue 使用。"""
    from app.services.accounting_service import get_agents_with_balance_and_projects
    result = await get_agents_with_balance_and_projects(db, page, page_size, status)
    return await _fill_agent_project_user_counts(db=db, result=result)


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

    return await get_agent_balance(agent_id, db)


@router.post("/agents/{agent_id}/recharge", summary="给代理充值点数")
async def recharge(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await recharge_agent(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.recharge",
        target_type="accounting_wallet",
        target_id=agent_id,
        summary=f"给代理 {agent_id} 充值 {body.amount} 点",
        metadata=_audit_wallet_metadata(
            agent_id=agent_id,
            amount=body.amount,
            description=body.description,
            wallet=result,
        ),
    )
    return result


@router.post("/agents/{agent_id}/credit", summary="给代理授信")
async def credit(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await credit_agent(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.credit",
        target_type="accounting_wallet",
        target_id=agent_id,
        summary=f"给代理 {agent_id} 授信 {body.amount} 点",
        metadata=_audit_wallet_metadata(
            agent_id=agent_id,
            amount=body.amount,
            description=body.description,
            wallet=result,
        ),
    )
    return result


@router.post("/agents/{agent_id}/freeze", summary="冻结代理授信")
async def freeze(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await freeze_credit(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.freeze",
        target_type="accounting_wallet",
        target_id=agent_id,
        summary=f"冻结代理 {agent_id} 授信 {body.amount} 点",
        metadata=_audit_wallet_metadata(
            agent_id=agent_id,
            amount=body.amount,
            description=body.description,
            wallet=result,
        ),
    )
    return result


@router.post("/agents/{agent_id}/unfreeze", summary="解冻代理授信")
async def unfreeze(
    agent_id: int,
    body: AccountingAmountRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await unfreeze_credit(
        agent_id=agent_id,
        amount=body.amount,
        description=body.description,
        admin_id=current_admin.id,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.unfreeze",
        target_type="accounting_wallet",
        target_id=agent_id,
        summary=f"解冻代理 {agent_id} 授信 {body.amount} 点",
        metadata=_audit_wallet_metadata(
            agent_id=agent_id,
            amount=body.amount,
            description=body.description,
            wallet=result,
        ),
    )
    return result


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


@router.post("/reconciliation/init-baseline", summary="初始化开发期账务基线")
async def reconciliation_init_baseline(
    agent_id: int | None = Query(default=None, description="只初始化指定代理；不填则初始化全部钱包"),
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await initialize_reconciliation_baseline(
        db=db,
        admin_id=current_admin.id,
        agent_id=agent_id,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.reconciliation.init_baseline",
        target_type="accounting_reconciliation",
        target_id=agent_id if agent_id is not None else "all",
        summary=(
            f"初始化代理 {agent_id} 账务基线"
            if agent_id is not None
            else "初始化全部代理账务基线"
        ),
        metadata=_audit_reconciliation_metadata(agent_id=agent_id, result=result),
    )
    return result


@router.post("/reconciliation/run", summary="运行账务对账")
async def reconciliation_run(
    agent_id: int | None = Query(default=None, description="只对账指定代理；不填则对账全部钱包"),
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await run_reconciliation(
        db=db,
        admin_id=current_admin.id,
        agent_id=agent_id,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="accounting.reconciliation.run",
        target_type="accounting_reconciliation",
        target_id=agent_id if agent_id is not None else "all",
        summary=(
            f"运行代理 {agent_id} 账务对账"
            if agent_id is not None
            else "运行全部代理账务对账"
        ),
        metadata=_audit_reconciliation_metadata(agent_id=agent_id, result=result),
    )
    return result


@router.get("/reconciliation/runs", summary="对账批次列表")
async def reconciliation_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None, description="running/completed/failed"),
    scope_type: str | None = Query(default=None, description="all/agent"),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await list_reconciliation_runs(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        scope_type=scope_type,
    )


@router.get("/reconciliation/runs/{run_id}", summary="对账批次详情")
async def reconciliation_run_detail(
    run_id: int,
    item_page: int = Query(default=1, ge=1),
    item_page_size: int = Query(default=100, ge=1, le=500),
    item_status: str | None = Query(default=None, description="normal/abnormal/pending_review/fixed"),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_reconciliation_run_detail(
        db=db,
        run_id=run_id,
        item_page=item_page,
        item_page_size=item_page_size,
        item_status=item_status,
    )
