r"""
文件位置: app/services/accounting_query_service.py
文件名称: accounting_query_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心读模型 / 查询服务。

设计边界:
    accounting_service.py:
        负责写操作与核心账务动作：
        充值、授信、冻结、解冻、授权扣点、删除返点、账本写入。

    accounting_query_service.py:
        负责账务中心页面需要的读模型：
        账务总览、代理钱包列表、扣点快照、返点记录。

说明:
    当前阶段以开发期直接重构为目标。
    旧 balance 接口暂时保留兼容，新前端应逐步切换到 /admin/api/accounting。
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.accounting import (
    AccountingLedgerEntry,
    AccountingWallet,
    AuthorizationChargeSnapshot,
)
from app.models.main.models import Agent, GameProject, User


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _today_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _wallet_row(wallet: AccountingWallet, agent: Agent | None = None) -> dict:
    charged = Decimal(str(wallet.charged_balance or 0))
    credit = Decimal(str(wallet.credit_balance or 0))
    frozen = Decimal(str(wallet.frozen_credit or 0))
    available_credit = credit - frozen
    available_total = charged + available_credit

    return {
        "wallet_id": wallet.id,
        "agent_id": wallet.agent_id,
        "agent_username": agent.username if agent else None,
        "agent_level": agent.level if agent else None,
        "agent_status": agent.status if agent else None,

        "charged_balance": _money(charged),
        "credit_balance": _money(credit),
        "frozen_credit": _money(frozen),
        "available_credit": _money(available_credit),
        "available_total": _money(available_total),

        "total_recharged": _money(wallet.total_recharged),
        "total_credited": _money(wallet.total_credited),
        "total_consumed": _money(wallet.total_consumed),
        "total_refunded": _money(wallet.total_refunded),
        "total_adjusted": _money(wallet.total_adjusted),

        "last_recharge_at": wallet.last_recharge_at,
        "last_credit_at": wallet.last_credit_at,
        "last_consume_at": wallet.last_consume_at,
        "last_refund_at": wallet.last_refund_at,

        "status": wallet.status,
        "risk_status": wallet.risk_status,
        "created_at": wallet.created_at,
        "updated_at": wallet.updated_at,

        # 旧字段兼容
        "charged_points": _money(charged),
        "credit_points": _money(credit),
        "recharge_balance": _money(charged),
    }


async def get_accounting_overview(db: AsyncSession) -> dict:
    """
    账务中心总览。

    当前口径:
        - 钱包余额来自 accounting_wallet。
        - 今日充值 / 授信 / 扣点 / 返点来自 accounting_ledger_entry。
    """
    wallet_totals = await db.execute(
        select(
            func.coalesce(func.sum(AccountingWallet.charged_balance), 0),
            func.coalesce(func.sum(AccountingWallet.credit_balance), 0),
            func.coalesce(func.sum(AccountingWallet.frozen_credit), 0),
            func.coalesce(func.sum(AccountingWallet.total_consumed), 0),
            func.coalesce(func.sum(AccountingWallet.total_refunded), 0),
            func.count(AccountingWallet.id),
        )
    )
    (
        total_charged,
        total_credit,
        total_frozen,
        total_consumed,
        total_refunded,
        wallet_count,
    ) = wallet_totals.one()

    today_start = _today_start_utc()

    today_rows = await db.execute(
        select(
            AccountingLedgerEntry.entry_type,
            AccountingLedgerEntry.direction,
            func.coalesce(func.sum(AccountingLedgerEntry.amount), 0),
        )
        .where(AccountingLedgerEntry.posted_at >= today_start)
        .group_by(AccountingLedgerEntry.entry_type, AccountingLedgerEntry.direction)
    )

    today_summary = {
        "today_recharge": 0.0,
        "today_credit": 0.0,
        "today_freeze": 0.0,
        "today_unfreeze": 0.0,
        "today_consume": 0.0,
        "today_refund": 0.0,
        "today_adjust": 0.0,
    }

    for entry_type, _direction, amount in today_rows.all():
        key = f"today_{entry_type}"
        if key in today_summary:
            today_summary[key] = _money(amount)

    total_charged_dec = Decimal(str(total_charged or 0))
    total_credit_dec = Decimal(str(total_credit or 0))
    total_frozen_dec = Decimal(str(total_frozen or 0))
    total_available_credit = total_credit_dec - total_frozen_dec
    total_available = total_charged_dec + total_available_credit

    pending_refund_rows = await db.execute(
        select(func.count(AuthorizationChargeSnapshot.id))
        .where(
            AuthorizationChargeSnapshot.refund_status == "none",
            AuthorizationChargeSnapshot.valid_until > datetime.now(timezone.utc),
        )
    )
    refundable_snapshot_count = pending_refund_rows.scalar_one()

    return {
        "wallet_count": int(wallet_count or 0),

        "total_charged_balance": _money(total_charged_dec),
        "total_credit_balance": _money(total_credit_dec),
        "total_frozen_credit": _money(total_frozen_dec),
        "total_available_credit": _money(total_available_credit),
        "total_available_balance": _money(total_available),

        "total_consumed": _money(total_consumed),
        "total_refunded": _money(total_refunded),

        "refundable_snapshot_count": int(refundable_snapshot_count or 0),

        **today_summary,
    }


async def list_accounting_wallets(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    status: str | None = None,
    risk_status: str | None = None,
    agent_id: int | None = None,
) -> dict:
    query = (
        select(AccountingWallet, Agent)
        .join(Agent, Agent.id == AccountingWallet.agent_id)
    )

    conditions = []

    if agent_id:
        conditions.append(AccountingWallet.agent_id == agent_id)

    if status:
        conditions.append(AccountingWallet.status == status)

    if risk_status:
        conditions.append(AccountingWallet.risk_status == risk_status)

    if keyword:
        kw = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                Agent.username.ilike(kw),
                Agent.contact.ilike(kw) if hasattr(Agent, "contact") else Agent.username.ilike(kw),
            )
        )

    if conditions:
        query = query.where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(AccountingWallet.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    rows = [
        _wallet_row(wallet, agent)
        for wallet, agent in result.all()
    ]

    return {
        "wallets": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_accounting_wallet_detail(agent_id: int, db: AsyncSession) -> dict | None:
    result = await db.execute(
        select(AccountingWallet, Agent)
        .join(Agent, Agent.id == AccountingWallet.agent_id)
        .where(AccountingWallet.agent_id == agent_id)
    )
    row = result.one_or_none()

    if not row:
        return None

    wallet, agent = row
    return _wallet_row(wallet, agent)


async def list_authorization_charge_snapshots(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    agent_id: int | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
    refund_status: str | None = None,
) -> dict:
    query = (
        select(AuthorizationChargeSnapshot, Agent, User, GameProject)
        .join(Agent, Agent.id == AuthorizationChargeSnapshot.agent_id)
        .join(User, User.id == AuthorizationChargeSnapshot.user_id)
        .join(GameProject, GameProject.id == AuthorizationChargeSnapshot.project_id)
    )

    conditions = []

    if agent_id:
        conditions.append(AuthorizationChargeSnapshot.agent_id == agent_id)

    if user_id:
        conditions.append(AuthorizationChargeSnapshot.user_id == user_id)

    if project_id:
        conditions.append(AuthorizationChargeSnapshot.project_id == project_id)

    if refund_status:
        conditions.append(AuthorizationChargeSnapshot.refund_status == refund_status)

    if conditions:
        query = query.where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(AuthorizationChargeSnapshot.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    rows = []

    for snapshot, agent, user, project in result.all():
        rows.append({
            "id": snapshot.id,
            "charge_snapshot_id": snapshot.id,
            "document_id": snapshot.document_id,
            "authorization_id": snapshot.authorization_id,

            "agent_id": snapshot.agent_id,
            "agent_username": agent.username,

            "user_id": snapshot.user_id,
            "user_username": user.username,

            "project_id": snapshot.project_id,
            "project_name": project.display_name,
            "project_code": project.code_name,

            "user_level": snapshot.user_level,
            "authorized_devices": snapshot.authorized_devices,

            "billing_period": snapshot.billing_period,
            "billing_period_hours": snapshot.billing_period_hours,
            "period_count": snapshot.period_count,
            "paid_hours": snapshot.paid_hours,

            "unit_price": _money(snapshot.unit_price),
            "original_cost": _money(snapshot.original_cost),
            "charged_consumed": _money(snapshot.charged_consumed),
            "credit_consumed": _money(snapshot.credit_consumed),

            "valid_from": snapshot.valid_from,
            "valid_until": snapshot.valid_until,

            "refund_status": snapshot.refund_status,
            "refunded_points": _money(snapshot.refunded_points),
            "refunded_charged": _money(snapshot.refunded_charged),
            "refunded_credit": _money(snapshot.refunded_credit),
            "refunded_at": snapshot.refunded_at,

            "last_refund_paid_hours": snapshot.last_refund_paid_hours,
            "last_refund_used_hours": snapshot.last_refund_used_hours,
            "last_refund_used_cost": _money(snapshot.last_refund_used_cost),
            "last_refund_points": _money(snapshot.last_refund_points),

            "created_at": snapshot.created_at,
        })

    return {
        "charges": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_refund_records(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    agent_id: int | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
) -> dict:
    query = (
        select(AuthorizationChargeSnapshot, Agent, User, GameProject)
        .join(Agent, Agent.id == AuthorizationChargeSnapshot.agent_id)
        .join(User, User.id == AuthorizationChargeSnapshot.user_id)
        .join(GameProject, GameProject.id == AuthorizationChargeSnapshot.project_id)
        .where(AuthorizationChargeSnapshot.refunded_points > 0)
    )

    conditions = []

    if agent_id:
        conditions.append(AuthorizationChargeSnapshot.agent_id == agent_id)

    if user_id:
        conditions.append(AuthorizationChargeSnapshot.user_id == user_id)

    if project_id:
        conditions.append(AuthorizationChargeSnapshot.project_id == project_id)

    if conditions:
        query = query.where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(
            AuthorizationChargeSnapshot.refunded_at.desc().nullslast(),
            AuthorizationChargeSnapshot.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    rows = []

    for snapshot, agent, user, project in result.all():
        rows.append({
            "id": snapshot.id,
            "charge_snapshot_id": snapshot.id,
            "authorization_id": snapshot.authorization_id,

            "agent_id": snapshot.agent_id,
            "agent_username": agent.username,

            "user_id": snapshot.user_id,
            "user_username": user.username,

            "project_id": snapshot.project_id,
            "project_name": project.display_name,
            "project_code": project.code_name,

            "user_level": snapshot.user_level,
            "authorized_devices": snapshot.authorized_devices,

            "original_cost": _money(snapshot.original_cost),
            "paid_hours": snapshot.paid_hours,

            "refunded_points": _money(snapshot.refunded_points),
            "refunded_charged": _money(snapshot.refunded_charged),
            "refunded_credit": _money(snapshot.refunded_credit),
            "refund_status": snapshot.refund_status,
            "refunded_at": snapshot.refunded_at,

            "last_refund_paid_hours": snapshot.last_refund_paid_hours,
            "last_refund_used_hours": snapshot.last_refund_used_hours,
            "last_refund_used_cost": _money(snapshot.last_refund_used_cost),
            "last_refund_points": _money(snapshot.last_refund_points),

            "created_at": snapshot.created_at,
        })

    return {
        "refunds": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }