r"""
文件位置: app/services/accounting_reconciliation_service.py
文件名称: accounting_reconciliation_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心对账服务。

核心职责:
    1. 初始化开发期账务基线。
    2. 运行钱包快照 vs 账本累计对账。
    3. 查询对账批次。
    4. 查询对账明细。

重要设计:
    accounting_wallet 是当前余额快照。
    accounting_ledger_entry 是不可变账本事实。

    对账公式:
      charged_balance = charged 类型账本累计
      credit_balance  = credit 类型账本累计，但不包含 freeze / unfreeze
      frozen_credit   = freeze 累计 - unfreeze 累计

开发期说明:
    因为当前处于开发期直接重构阶段，旧 agent_balance 已迁移到 accounting_wallet，
    但旧 balance_transaction 没有完整迁移为 accounting_ledger_entry。

    因此提供 init_baseline 功能，把当前钱包余额写成一组基线账本记录：
      - charged_balance > 0 生成 adjust / charged / in
      - credit_balance > 0 生成 adjust / credit / in
      - frozen_credit > 0 生成 freeze / credit / out

    该操作带 idempotency_key，重复执行不会重复写入。
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.accounting import (
    AccountingDocument,
    AccountingLedgerEntry,
    AccountingReconciliationItem,
    AccountingReconciliationRun,
    AccountingWallet,
)
from app.models.main.models import Agent


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_float(value: Any) -> float:
    return float(_money(value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_no(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"


async def _has_idempotency_key(db: AsyncSession, key: str) -> bool:
    result = await db.execute(
        select(AccountingLedgerEntry.id).where(AccountingLedgerEntry.idempotency_key == key)
    )
    return result.scalar_one_or_none() is not None


async def _create_document(
    *,
    db: AsyncSession,
    document_type: str,
    agent_id: int,
    total_amount: Decimal,
    reason: str,
    created_by_admin_id: int | None,
) -> AccountingDocument:
    document = AccountingDocument(
        document_no=_make_no("AD"),
        document_type=document_type,
        agent_id=agent_id,
        total_amount=_money(total_amount),
        status="posted",
        reason=reason,
        created_by_admin_id=created_by_admin_id,
        posted_at=_now(),
    )
    db.add(document)
    await db.flush()
    return document


async def _append_baseline_entry(
    *,
    db: AsyncSession,
    wallet: AccountingWallet,
    document: AccountingDocument,
    direction: str,
    entry_type: str,
    balance_type: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    business_subtype: str,
    idempotency_key: str,
    admin_id: int | None,
    description: str,
) -> AccountingLedgerEntry:
    entry = AccountingLedgerEntry(
        entry_no=_make_no("PL"),
        wallet_id=wallet.id,
        agent_id=wallet.agent_id,
        direction=direction,
        entry_type=entry_type,
        balance_type=balance_type,
        amount=_money(amount),
        balance_before=_money(balance_before),
        balance_after=_money(balance_after),
        business_category="migration_baseline",
        business_subtype=business_subtype,
        related_document_id=document.id,
        description=description,
        business_text=description,
        idempotency_key=idempotency_key,
        source="system",
        status="posted",
        operated_by_admin_id=admin_id,
        posted_at=_now(),
    )
    db.add(entry)
    await db.flush()
    return entry


async def initialize_reconciliation_baseline(
    *,
    db: AsyncSession,
    admin_id: int | None,
    agent_id: int | None = None,
) -> dict:
    """
    初始化开发期账务基线。

    适用场景:
        旧 agent_balance 已迁移到 accounting_wallet，
        但新 accounting_ledger_entry 没有完整历史账本。

    幂等:
        每个 wallet 的 charged / credit / frozen 基线都有唯一 idempotency_key。
        重复执行不会重复写入。
    """
    query = select(AccountingWallet)

    if agent_id:
        query = query.where(AccountingWallet.agent_id == agent_id)

    result = await db.execute(query.order_by(AccountingWallet.agent_id.asc()))
    wallets = result.scalars().all()

    created_documents = 0
    created_entries = 0
    skipped_wallets = 0
    touched_wallets = 0

    for wallet in wallets:
        charged = _money(wallet.charged_balance)
        credit = _money(wallet.credit_balance)
        frozen = _money(wallet.frozen_credit)

        charged_key = f"baseline:wallet:{wallet.id}:charged"
        credit_key = f"baseline:wallet:{wallet.id}:credit"
        frozen_key = f"baseline:wallet:{wallet.id}:frozen"

        need_charged = charged > 0 and not await _has_idempotency_key(db, charged_key)
        need_credit = credit > 0 and not await _has_idempotency_key(db, credit_key)
        need_frozen = frozen > 0 and not await _has_idempotency_key(db, frozen_key)

        if not need_charged and not need_credit and not need_frozen:
            skipped_wallets += 1
            continue

        total_amount = Decimal("0.00")
        if need_charged:
            total_amount += charged
        if need_credit:
            total_amount += credit
        if need_frozen:
            total_amount += frozen

        document = await _create_document(
            db=db,
            document_type="reconciliation_adjust",
            agent_id=wallet.agent_id,
            total_amount=total_amount,
            reason="开发期账务中心重构：初始化钱包基线账本",
            created_by_admin_id=admin_id,
        )
        created_documents += 1
        touched_wallets += 1

        if need_charged:
            await _append_baseline_entry(
                db=db,
                wallet=wallet,
                document=document,
                direction="in",
                entry_type="adjust",
                balance_type="charged",
                amount=charged,
                balance_before=Decimal("0.00"),
                balance_after=charged,
                business_subtype="baseline_charged",
                idempotency_key=charged_key,
                admin_id=admin_id,
                description=f"开发期基线：代理ID={wallet.agent_id} 充值点数余额 {_money_float(charged):.2f}",
            )
            created_entries += 1

        if need_credit:
            await _append_baseline_entry(
                db=db,
                wallet=wallet,
                document=document,
                direction="in",
                entry_type="adjust",
                balance_type="credit",
                amount=credit,
                balance_before=Decimal("0.00"),
                balance_after=credit,
                business_subtype="baseline_credit",
                idempotency_key=credit_key,
                admin_id=admin_id,
                description=f"开发期基线：代理ID={wallet.agent_id} 授信点数余额 {_money_float(credit):.2f}",
            )
            created_entries += 1

        if need_frozen:
            available_before = credit
            available_after = credit - frozen

            await _append_baseline_entry(
                db=db,
                wallet=wallet,
                document=document,
                direction="out",
                entry_type="freeze",
                balance_type="credit",
                amount=frozen,
                balance_before=available_before,
                balance_after=available_after,
                business_subtype="baseline_frozen_credit",
                idempotency_key=frozen_key,
                admin_id=admin_id,
                description=f"开发期基线：代理ID={wallet.agent_id} 冻结授信 {_money_float(frozen):.2f}",
            )
            created_entries += 1

    await db.flush()

    return {
        "wallet_count": len(wallets),
        "touched_wallets": touched_wallets,
        "skipped_wallets": skipped_wallets,
        "created_documents": created_documents,
        "created_entries": created_entries,
    }


async def _calculate_wallet_from_ledger(
    *,
    db: AsyncSession,
    agent_id: int,
) -> dict:
    result = await db.execute(
        select(AccountingLedgerEntry)
        .where(
            AccountingLedgerEntry.agent_id == agent_id,
            AccountingLedgerEntry.status == "posted",
        )
        .order_by(AccountingLedgerEntry.id.asc())
    )

    entries = result.scalars().all()

    charged_balance = Decimal("0.00")
    credit_balance = Decimal("0.00")
    frozen_credit = Decimal("0.00")

    for entry in entries:
        amount = _money(entry.amount)

        if entry.balance_type == "charged":
            if entry.direction == "in":
                charged_balance += amount
            else:
                charged_balance -= amount
            continue

        if entry.balance_type == "credit":
            if entry.entry_type == "freeze":
                frozen_credit += amount
                continue

            if entry.entry_type == "unfreeze":
                frozen_credit -= amount
                continue

            if entry.direction == "in":
                credit_balance += amount
            else:
                credit_balance -= amount

    return {
        "charged_balance": _money(charged_balance),
        "credit_balance": _money(credit_balance),
        "frozen_credit": _money(frozen_credit),
        "entry_count": len(entries),
    }


def _diff(snapshot: Decimal, calculated: Decimal) -> Decimal:
    return _money(snapshot - calculated)


def _item_status(
    charged_diff: Decimal,
    credit_diff: Decimal,
    frozen_diff: Decimal,
) -> str:
    if charged_diff == 0 and credit_diff == 0 and frozen_diff == 0:
        return "normal"
    return "abnormal"


async def run_reconciliation(
    *,
    db: AsyncSession,
    admin_id: int | None,
    agent_id: int | None = None,
) -> dict:
    """
    运行对账。

    对账目标:
        accounting_wallet 当前快照
        vs
        accounting_ledger_entry 账本累计
    """
    scope_type = "agent" if agent_id else "all"

    run = AccountingReconciliationRun(
        run_no=_make_no("AR"),
        scope_type=scope_type,
        scope_agent_id=agent_id,
        started_at=_now(),
        status="running",
        created_by_admin_id=admin_id,
    )
    db.add(run)
    await db.flush()

    query = select(AccountingWallet)

    if agent_id:
        query = query.where(AccountingWallet.agent_id == agent_id)

    result = await db.execute(query.order_by(AccountingWallet.agent_id.asc()))
    wallets = result.scalars().all()

    normal_count = 0
    abnormal_count = 0

    for wallet in wallets:
        snapshot_charged = _money(wallet.charged_balance)
        snapshot_credit = _money(wallet.credit_balance)
        snapshot_frozen = _money(wallet.frozen_credit)

        calculated = await _calculate_wallet_from_ledger(
            db=db,
            agent_id=wallet.agent_id,
        )

        calculated_charged = calculated["charged_balance"]
        calculated_credit = calculated["credit_balance"]
        calculated_frozen = calculated["frozen_credit"]

        charged_diff = _diff(snapshot_charged, calculated_charged)
        credit_diff = _diff(snapshot_credit, calculated_credit)
        frozen_diff = _diff(snapshot_frozen, calculated_frozen)

        status = _item_status(charged_diff, credit_diff, frozen_diff)

        if status == "normal":
            normal_count += 1
        else:
            abnormal_count += 1

        issue_detail = None
        if status != "normal":
            issue_detail = {
                "message": "钱包快照与账本累计不一致",
                "entry_count": calculated["entry_count"],
                "charged": {
                    "snapshot": _money_float(snapshot_charged),
                    "calculated": _money_float(calculated_charged),
                    "diff": _money_float(charged_diff),
                },
                "credit": {
                    "snapshot": _money_float(snapshot_credit),
                    "calculated": _money_float(calculated_credit),
                    "diff": _money_float(credit_diff),
                },
                "frozen": {
                    "snapshot": _money_float(snapshot_frozen),
                    "calculated": _money_float(calculated_frozen),
                    "diff": _money_float(frozen_diff),
                },
            }

        item = AccountingReconciliationItem(
            run_id=run.id,
            agent_id=wallet.agent_id,
            charged_balance_snapshot=snapshot_charged,
            charged_balance_calculated=calculated_charged,
            charged_diff=charged_diff,
            credit_balance_snapshot=snapshot_credit,
            credit_balance_calculated=calculated_credit,
            credit_diff=credit_diff,
            frozen_credit_snapshot=snapshot_frozen,
            frozen_credit_calculated=calculated_frozen,
            frozen_diff=frozen_diff,
            status=status,
            issue_detail=issue_detail,
        )
        db.add(item)

    run.checked_wallets = len(wallets)
    run.normal_count = normal_count
    run.abnormal_count = abnormal_count
    run.status = "completed"
    run.finished_at = _now()
    run.summary = {
        "scope_type": scope_type,
        "scope_agent_id": agent_id,
        "checked_wallets": len(wallets),
        "normal_count": normal_count,
        "abnormal_count": abnormal_count,
    }

    await db.flush()

    return {
        "run_id": run.id,
        "run_no": run.run_no,
        "scope_type": run.scope_type,
        "scope_agent_id": run.scope_agent_id,
        "status": run.status,
        "checked_wallets": run.checked_wallets,
        "normal_count": run.normal_count,
        "abnormal_count": run.abnormal_count,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


async def list_reconciliation_runs(
    *,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    scope_type: str | None = None,
) -> dict:
    query = select(AccountingReconciliationRun)

    conditions = []

    if status:
        conditions.append(AccountingReconciliationRun.status == status)

    if scope_type:
        conditions.append(AccountingReconciliationRun.scope_type == scope_type)

    if conditions:
        query = query.where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(AccountingReconciliationRun.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    runs = result.scalars().all()

    return {
        "runs": [
            {
                "id": run.id,
                "run_no": run.run_no,
                "scope_type": run.scope_type,
                "scope_agent_id": run.scope_agent_id,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "status": run.status,
                "checked_wallets": run.checked_wallets,
                "normal_count": run.normal_count,
                "abnormal_count": run.abnormal_count,
                "summary": run.summary,
                "created_by_admin_id": run.created_by_admin_id,
                "created_at": run.created_at,
            }
            for run in runs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_reconciliation_run_detail(
    *,
    db: AsyncSession,
    run_id: int,
    item_page: int = 1,
    item_page_size: int = 100,
    item_status: str | None = None,
) -> dict:
    run = await db.get(AccountingReconciliationRun, run_id)

    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对账批次不存在")

    item_query = select(AccountingReconciliationItem).where(
        AccountingReconciliationItem.run_id == run_id
    )

    if item_status:
        item_query = item_query.where(AccountingReconciliationItem.status == item_status)

    total = (
        await db.execute(select(func.count()).select_from(item_query.subquery()))
    ).scalar_one()

    offset = (item_page - 1) * item_page_size

    item_result = await db.execute(
        item_query.order_by(
            AccountingReconciliationItem.status.desc(),
            AccountingReconciliationItem.id.asc(),
        )
        .offset(offset)
        .limit(item_page_size)
    )

    items = item_result.scalars().all()
    agent_ids = {item.agent_id for item in items}

    agent_map: dict[int, Agent] = {}

    if agent_ids:
        agent_result = await db.execute(
            select(Agent).where(Agent.id.in_(agent_ids))
        )
        agent_map = {agent.id: agent for agent in agent_result.scalars().all()}

    return {
        "run": {
            "id": run.id,
            "run_no": run.run_no,
            "scope_type": run.scope_type,
            "scope_agent_id": run.scope_agent_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status,
            "checked_wallets": run.checked_wallets,
            "normal_count": run.normal_count,
            "abnormal_count": run.abnormal_count,
            "summary": run.summary,
            "created_by_admin_id": run.created_by_admin_id,
            "created_at": run.created_at,
        },
        "items": [
            {
                "id": item.id,
                "run_id": item.run_id,
                "agent_id": item.agent_id,
                "agent_username": agent_map[item.agent_id].username if item.agent_id in agent_map else None,

                "charged_balance_snapshot": _money_float(item.charged_balance_snapshot),
                "charged_balance_calculated": _money_float(item.charged_balance_calculated),
                "charged_diff": _money_float(item.charged_diff),

                "credit_balance_snapshot": _money_float(item.credit_balance_snapshot),
                "credit_balance_calculated": _money_float(item.credit_balance_calculated),
                "credit_diff": _money_float(item.credit_diff),

                "frozen_credit_snapshot": _money_float(item.frozen_credit_snapshot),
                "frozen_credit_calculated": _money_float(item.frozen_credit_calculated),
                "frozen_diff": _money_float(item.frozen_diff),

                "status": item.status,
                "issue_detail": item.issue_detail,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "total": total,
        "page": item_page,
        "page_size": item_page_size,
    }