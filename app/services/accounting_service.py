r"""
文件位置: app/services/accounting_service.py
文件名称: accounting_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心服务层。

核心职责:
    - 项目定价
    - 代理钱包
    - 充值
    - 授信
    - 冻结 / 解冻
    - 授权扣点
    - 删除用户返点
    - 点数账本查询
    - 代理列表账务聚合

当前重构口径:
    - AccountingWallet 是代理钱包快照。
    - AccountingDocument 是一次账务业务单据。
    - AccountingLedgerEntry 是不可变账本明细。
    - AuthorizationChargeSnapshot 是授权扣点快照。
"""

import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.accounting import (
    AccountingDocument,
    AccountingLedgerEntry,
    AccountingWallet,
    AuthorizationChargeSnapshot,
)
from app.models.main.models import (
    Admin,
    Agent,
    AgentProjectAuth,
    GameProject,
    ProjectPrice,
    User,
)


LEVEL_NAMES = {
    "trial": "试用",
    "normal": "普通",
    "vip": "VIP",
    "svip": "SVIP",
    "tester": "测试",
}

PRICING_LEVELS = ["trial", "normal", "vip", "svip"]

BILLING_RULES = {
    "trial": {
        "period": "week",
        "period_days": 7,
        "period_hours": 168,
        "period_name": "周",
        "unit_label": "每周/台",
    },
    "normal": {
        "period": "month",
        "period_days": 30,
        "period_hours": 720,
        "period_name": "月",
        "unit_label": "每月/台",
    },
    "vip": {
        "period": "month",
        "period_days": 30,
        "period_hours": 720,
        "period_name": "月",
        "unit_label": "每月/台",
    },
    "svip": {
        "period": "month",
        "period_days": 30,
        "period_hours": 720,
        "period_name": "月",
        "unit_label": "每月/台",
    },
}

TX_TYPE_LABELS = {
    "recharge": "充值",
    "credit": "授信",
    "consume": "授权扣点",
    "refund": "删除返点",
    "freeze": "冻结",
    "unfreeze": "解冻",
    "adjust": "调整",
    "reversal": "冲正",
}

BALANCE_TYPE_LABELS = {
    "charged": "充值点数",
    "credit": "授信点数",
}


# ─────────────────────────────────────────────────────────────
# 基础工具（本地特有函数 + 共享模块别名）
# ─────────────────────────────────────────────────────────────

from app.core.utils import (
    ensure_aware as _ensure_aware,
    money as _money,
    make_business_no as _make_no,
    now_utc as _now,
)


def _fmt_money(value: float | Decimal | int | str | None) -> str:
    return f"{float(_money(value)):.2f}"


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "永久"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _ceil_hours(start_at: datetime, end_at: datetime) -> int:
    start_at = _ensure_aware(start_at)
    end_at = _ensure_aware(end_at)

    seconds = (end_at - start_at).total_seconds()
    if seconds <= 0:
        return 0

    return max(1, math.ceil(seconds / 3600))


def _calc_period_count(user_level: str, start_at: datetime, end_at: datetime) -> int:
    if user_level not in BILLING_RULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户级别 {user_level} 不支持代理计费",
        )

    raw_hours = _ceil_hours(start_at, end_at)
    if raw_hours <= 0:
        return 0

    period_hours = BILLING_RULES[user_level]["period_hours"]
    return max(1, math.ceil(raw_hours / period_hours))


def _signed_amount(entry: AccountingLedgerEntry) -> float:
    """
    将账本金额转为带符号金额。

    规则:
      - consume / freeze → 负数（余额减少）
      - unfreeze / refund / recharge / credit → 正数（余额增加）
      - reversal: 根据 direction 判断
      - 其他: 根据 direction 判断
    """
    amount = _money(entry.amount)

    # 明确消耗类 → 负数
    if entry.entry_type in {"consume", "freeze"}:
        return -float(amount)

    # 明确增加类 → 正数
    if entry.entry_type in {"unfreeze", "refund", "recharge", "credit"}:
        return float(amount)

    if entry.entry_type == "reversal":
        return -float(amount) if entry.direction == "out" else float(amount)

    if entry.direction == "out":
        return -float(amount)

    return float(amount)


# ─────────────────────────────────────────────────────────────
# 项目定价
# ─────────────────────────────────────────────────────────────

async def get_project_prices(project_id: int, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(ProjectPrice)
        .where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level.in_(PRICING_LEVELS),
        )
    )
    prices = {p.user_level: p for p in result.scalars().all()}

    return [
        {
            "user_level": level,
            "level_name": LEVEL_NAMES[level],
            "billing_period": BILLING_RULES[level]["period"],
            "billing_period_name": BILLING_RULES[level]["period_name"],
            "billing_period_hours": BILLING_RULES[level]["period_hours"],
            "unit_label": BILLING_RULES[level]["unit_label"],
            "points_per_device": float(_money(prices[level].points_per_device)) if level in prices else None,
            "price_id": prices[level].id if level in prices else None,
        }
        for level in PRICING_LEVELS
    ]


async def set_project_price(
    project_id: int,
    user_level: str,
    points_per_device: float,
    db: AsyncSession,
) -> dict:
    if user_level not in PRICING_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不可售卖用户级别: {user_level}")

    if points_per_device < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="点数不能为负数")

    from app.core.utils import get_project_or_404
    project = await get_project_or_404(project_id, db)

    normalized = _money(points_per_device)

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()

    if price:
        price.points_per_device = normalized
    else:
        price = ProjectPrice(
            project_id=project_id,
            user_level=user_level,
            points_per_device=normalized,
        )
        db.add(price)

    await db.flush()

    return {
        "user_level": user_level,
        "level_name": LEVEL_NAMES[user_level],
        "billing_period": BILLING_RULES[user_level]["period"],
        "billing_period_name": BILLING_RULES[user_level]["period_name"],
        "billing_period_hours": BILLING_RULES[user_level]["period_hours"],
        "unit_label": BILLING_RULES[user_level]["unit_label"],
        "points_per_device": float(_money(price.points_per_device)),
        "price_id": price.id,
    }


async def delete_project_price(project_id: int, user_level: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()

    if not price:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定价记录不存在")

    await db.delete(price)
    await db.flush()


# ─────────────────────────────────────────────────────────────
# 钱包与账本底层
# ─────────────────────────────────────────────────────────────

async def get_or_create_wallet(agent_id: int, db: AsyncSession) -> AccountingWallet:
    result = await db.execute(
        select(AccountingWallet).where(AccountingWallet.agent_id == agent_id)
    )
    wallet = result.scalar_one_or_none()

    if wallet:
        return wallet

    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在")

    wallet = AccountingWallet(agent_id=agent_id)
    db.add(wallet)
    await db.flush()

    return wallet


async def _create_document(
    *,
    document_type: str,
    agent_id: int,
    db: AsyncSession,
    total_amount: Decimal,
    user_id: int | None = None,
    project_id: int | None = None,
    authorization_id: int | None = None,
    reason: str | None = None,
    remark: str | None = None,
    created_by_admin_id: int | None = None,
    created_by_agent_id: int | None = None,
) -> AccountingDocument:
    document = AccountingDocument(
        document_no=_make_no("AD"),
        document_type=document_type,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        authorization_id=authorization_id,
        total_amount=_money(total_amount),
        status="posted",
        reason=reason,
        remark=remark,
        created_by_admin_id=created_by_admin_id,
        created_by_agent_id=created_by_agent_id,
        posted_at=_now(),
    )
    db.add(document)
    await db.flush()
    return document


async def _append_ledger_entry(
    *,
    db: AsyncSession,
    wallet: AccountingWallet,
    document: AccountingDocument | None,
    direction: str,
    entry_type: str,
    balance_type: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    business_category: str,
    business_subtype: str | None = None,
    related_user_id: int | None = None,
    related_project_id: int | None = None,
    related_authorization_id: int | None = None,
    related_charge_snapshot_id: int | None = None,
    description: str | None = None,
    business_text: str | None = None,
    idempotency_key: str | None = None,
    source: str = "admin",
    operated_by_admin_id: int | None = None,
    operated_by_agent_id: int | None = None,
) -> AccountingLedgerEntry:
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账本金额必须大于 0")

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
        business_category=business_category,
        business_subtype=business_subtype,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
        related_authorization_id=related_authorization_id,
        related_charge_snapshot_id=related_charge_snapshot_id,
        related_document_id=document.id if document else None,
        description=description,
        business_text=business_text or description,
        idempotency_key=idempotency_key,
        source=source,
        status="posted",
        operated_by_admin_id=operated_by_admin_id,
        operated_by_agent_id=operated_by_agent_id,
        posted_at=_now(),
    )
    db.add(entry)
    await db.flush()
    return entry


def _wallet_response(wallet: AccountingWallet) -> dict:
    charged = _money(wallet.charged_balance)
    credit = _money(wallet.credit_balance)
    frozen = _money(wallet.frozen_credit)

    available_credit = credit - frozen
    available_total = charged + available_credit

    return {
        "agent_id": wallet.agent_id,

        # 新口径
        "charged_balance": float(charged),
        "credit_balance": float(credit),
        "frozen_credit": float(frozen),
        "available_credit": float(available_credit),
        "available_total": float(available_total),
        "total_recharged": float(_money(wallet.total_recharged)),
        "total_credited": float(_money(wallet.total_credited)),
        "total_consumed": float(_money(wallet.total_consumed)),
        "total_refunded": float(_money(wallet.total_refunded)),
        "total_adjusted": float(_money(wallet.total_adjusted)),
        "status": wallet.status,
        "risk_status": wallet.risk_status,

        # 旧前端兼容字段
        "charged_points": float(charged),
        "credit_points": float(credit),
        "recharge_balance": float(charged),
    }


async def get_agent_balance(agent_id: int, db: AsyncSession) -> dict:
    wallet = await get_or_create_wallet(agent_id, db)
    return _wallet_response(wallet)


# ─────────────────────────────────────────────────────────────
# 管理员账务操作
# ─────────────────────────────────────────────────────────────

async def recharge_agent(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="充值金额必须大于 0")

    amount_dec = _money(amount)
    wallet = await get_or_create_wallet(agent_id, db)

    document = await _create_document(
        document_type="recharge",
        agent_id=agent_id,
        db=db,
        total_amount=amount_dec,
        reason=description,
        created_by_admin_id=admin_id,
    )

    before = _money(wallet.charged_balance)
    after = before + amount_dec

    wallet.charged_balance = after
    wallet.total_recharged = _money(wallet.total_recharged) + amount_dec
    wallet.last_recharge_at = _now()

    text = description or f"管理员充值 {_fmt_money(amount_dec)} 点"

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="in",
        entry_type="recharge",
        balance_type="charged",
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        business_category="admin_grant",
        business_subtype="recharge",
        description=text,
        operated_by_admin_id=admin_id,
    )

    await db.flush()
    return await get_agent_balance(agent_id, db)


async def credit_agent(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授信金额必须大于 0")

    amount_dec = _money(amount)
    wallet = await get_or_create_wallet(agent_id, db)

    document = await _create_document(
        document_type="credit",
        agent_id=agent_id,
        db=db,
        total_amount=amount_dec,
        reason=description,
        created_by_admin_id=admin_id,
    )

    before = _money(wallet.credit_balance)
    after = before + amount_dec

    wallet.credit_balance = after
    wallet.total_credited = _money(wallet.total_credited) + amount_dec
    wallet.last_credit_at = _now()

    text = description or f"管理员授信 {_fmt_money(amount_dec)} 点"

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="in",
        entry_type="credit",
        balance_type="credit",
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        business_category="admin_grant",
        business_subtype="credit",
        description=text,
        operated_by_admin_id=admin_id,
    )

    await db.flush()
    return await get_agent_balance(agent_id, db)


async def freeze_credit(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="冻结金额必须大于 0")

    amount_dec = _money(amount)
    wallet = await get_or_create_wallet(agent_id, db)

    credit = _money(wallet.credit_balance)
    frozen = _money(wallet.frozen_credit)
    available_credit = credit - frozen

    if amount_dec > available_credit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"可冻结授信不足（可用授信: {available_credit} 点，请求冻结: {amount_dec} 点）",
        )

    document = await _create_document(
        document_type="freeze",
        agent_id=agent_id,
        db=db,
        total_amount=amount_dec,
        reason=description,
        created_by_admin_id=admin_id,
    )

    before_available = available_credit
    after_available = available_credit - amount_dec

    wallet.frozen_credit = frozen + amount_dec

    text = description or f"冻结授信 {_fmt_money(amount_dec)} 点"

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="out",
        entry_type="freeze",
        balance_type="credit",
        amount=amount_dec,
        balance_before=before_available,
        balance_after=after_available,
        business_category="credit_control",
        business_subtype="freeze",
        description=text,
        operated_by_admin_id=admin_id,
    )

    await db.flush()
    return await get_agent_balance(agent_id, db)


async def unfreeze_credit(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="解冻金额必须大于 0")

    amount_dec = _money(amount)
    wallet = await get_or_create_wallet(agent_id, db)

    frozen = _money(wallet.frozen_credit)

    if amount_dec > frozen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"已冻结金额不足（已冻结: {frozen} 点，请求解冻: {amount_dec} 点）",
        )

    credit = _money(wallet.credit_balance)
    available_credit = credit - frozen

    document = await _create_document(
        document_type="unfreeze",
        agent_id=agent_id,
        db=db,
        total_amount=amount_dec,
        reason=description,
        created_by_admin_id=admin_id,
    )

    before_available = available_credit
    after_available = available_credit + amount_dec

    wallet.frozen_credit = frozen - amount_dec

    text = description or f"解冻授信 {_fmt_money(amount_dec)} 点"

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="in",
        entry_type="unfreeze",
        balance_type="credit",
        amount=amount_dec,
        balance_before=before_available,
        balance_after=after_available,
        business_category="credit_control",
        business_subtype="unfreeze",
        description=text,
        operated_by_admin_id=admin_id,
    )

    await db.flush()
    return await get_agent_balance(agent_id, db)


# ─────────────────────────────────────────────────────────────
# 授权扣点
# ─────────────────────────────────────────────────────────────

async def calculate_authorization_cost(
    *,
    project_id: int,
    user_level: str,
    authorized_devices: int,
    start_at: datetime,
    valid_until: datetime,
    db: AsyncSession,
) -> dict:
    if user_level not in PRICING_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"用户级别 {user_level} 不支持代理计费")

    if authorized_devices <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理授权设备数必须大于 0")

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()

    if not price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该项目尚未设置 {LEVEL_NAMES.get(user_level, user_level)} 级别定价",
        )

    period_count = _calc_period_count(user_level, start_at, valid_until)
    if period_count <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权到期时间必须晚于授权开始时间")

    unit_price = _money(price.points_per_device)
    period_hours = BILLING_RULES[user_level]["period_hours"]
    paid_hours = period_hours * period_count
    total_cost = _money(unit_price * Decimal(authorized_devices) * Decimal(period_count))

    return {
        "project_id": project_id,
        "user_level": user_level,
        "level_name": LEVEL_NAMES[user_level],
        "unit_price": float(unit_price),
        "authorized_devices": authorized_devices,
        "period_count": period_count,
        "billing_period": BILLING_RULES[user_level]["period"],
        "billing_period_name": BILLING_RULES[user_level]["period_name"],
        "billing_period_hours": period_hours,
        "paid_hours": paid_hours,
        "unit_label": BILLING_RULES[user_level]["unit_label"],
        "total_cost": float(total_cost),
    }


async def consume_agent_authorization_points(
    *,
    agent_id: int,
    user_id: int,
    project_id: int,
    authorization_id: int,
    user_level: str,
    authorized_devices: int,
    start_at: datetime,
    valid_until: datetime,
    db: AsyncSession,
) -> dict:
    cost = await calculate_authorization_cost(
        project_id=project_id,
        user_level=user_level,
        authorized_devices=authorized_devices,
        start_at=start_at,
        valid_until=valid_until,
        db=db,
    )

    total_cost = _money(cost["total_cost"])
    if total_cost <= 0:
        return {
            "total_cost": 0.0,
            "charge_id": None,
            "charge_snapshot_id": None,
            "charged_consumed": 0.0,
            "credit_consumed": 0.0,
        }

    wallet = await get_or_create_wallet(agent_id, db)

    charged = _money(wallet.charged_balance)
    credit = _money(wallet.credit_balance)
    frozen = _money(wallet.frozen_credit)
    available_credit = credit - frozen
    available_total = charged + available_credit

    if total_cost > available_total:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"代理点数不足：需扣 {total_cost} 点，当前可用 {available_total} 点",
        )

    document = await _create_document(
        document_type="authorization_charge",
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        authorization_id=authorization_id,
        db=db,
        total_amount=total_cost,
        reason="用户项目授权扣点",
        created_by_agent_id=agent_id,
    )

    snapshot = AuthorizationChargeSnapshot(
        document_id=document.id,
        authorization_id=authorization_id,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        user_level=user_level,
        authorized_devices=authorized_devices,
        billing_period=cost["billing_period"],
        billing_period_hours=cost["billing_period_hours"],
        period_count=cost["period_count"],
        paid_hours=cost["paid_hours"],
        unit_price=_money(cost["unit_price"]),
        original_cost=total_cost,
        charged_consumed=Decimal("0.00"),
        credit_consumed=Decimal("0.00"),
        valid_from=_ensure_aware(start_at),
        valid_until=_ensure_aware(valid_until),
        refund_status="none",
        refunded_points=Decimal("0.00"),
        refunded_charged=Decimal("0.00"),
        refunded_credit=Decimal("0.00"),
    )
    db.add(snapshot)
    await db.flush()

    description = (
        f"用户项目授权扣点：用户ID={user_id}，项目ID={project_id}，"
        f"{cost['level_name']}，{authorized_devices}台，"
        f"单价{_fmt_money(cost['unit_price'])}点/{cost['unit_label']}，"
        f"{cost['period_count']}{cost['billing_period_name']}，"
        f"购买{cost['paid_hours']}小时，到期{_fmt_dt(valid_until)}，"
        f"合计{_fmt_money(total_cost)}点"
    )

    remaining = total_cost
    charged_consumed = Decimal("0.00")
    credit_consumed = Decimal("0.00")

    if charged > 0 and remaining > 0:
        consume_charged = min(charged, remaining)
        before = charged
        after = charged - consume_charged

        wallet.charged_balance = after
        remaining -= consume_charged
        charged_consumed = consume_charged

        await _append_ledger_entry(
            db=db,
            wallet=wallet,
            document=document,
            direction="out",
            entry_type="consume",
            balance_type="charged",
            amount=consume_charged,
            balance_before=before,
            balance_after=after,
            business_category="authorization_charge",
            business_subtype="consume_charged",
            related_user_id=user_id,
            related_project_id=project_id,
            related_authorization_id=authorization_id,
            related_charge_snapshot_id=snapshot.id,
            description=description,
            idempotency_key=f"authorization:{authorization_id}:charged",
            source="agent",
            operated_by_agent_id=agent_id,
        )

    if remaining > 0:
        before = credit
        after = credit - remaining

        wallet.credit_balance = after
        credit_consumed = remaining

        await _append_ledger_entry(
            db=db,
            wallet=wallet,
            document=document,
            direction="out",
            entry_type="consume",
            balance_type="credit",
            amount=remaining,
            balance_before=before,
            balance_after=after,
            business_category="authorization_charge",
            business_subtype="consume_credit",
            related_user_id=user_id,
            related_project_id=project_id,
            related_authorization_id=authorization_id,
            related_charge_snapshot_id=snapshot.id,
            description=description,
            idempotency_key=f"authorization:{authorization_id}:credit",
            source="agent",
            operated_by_agent_id=agent_id,
        )

    snapshot.charged_consumed = _money(charged_consumed)
    snapshot.credit_consumed = _money(credit_consumed)

    wallet.total_consumed = _money(wallet.total_consumed) + total_cost
    wallet.last_consume_at = _now()

    await db.flush()

    return {
        "total_cost": float(total_cost),
        "charge_id": snapshot.id,
        "charge_snapshot_id": snapshot.id,
        "charged_consumed": float(_money(charged_consumed)),
        "credit_consumed": float(_money(credit_consumed)),
    }


# ─────────────────────────────────────────────────────────────
# 删除用户返点
# ─────────────────────────────────────────────────────────────

async def refund_user_authorization_points_on_delete(
    *,
    user_id: int,
    db: AsyncSession,
    delete_time: datetime | None = None,
) -> dict:
    now = _ensure_aware(delete_time or _now())

    result = await db.execute(
        select(AuthorizationChargeSnapshot)
        .where(
            AuthorizationChargeSnapshot.user_id == user_id,
            AuthorizationChargeSnapshot.refund_status == "none",
            AuthorizationChargeSnapshot.valid_until > now,
        )
        .order_by(AuthorizationChargeSnapshot.id.asc())
    )
    snapshots = result.scalars().all()

    summary = {
        "user_id": user_id,
        "refunded_total": 0.0,
        "refunded_charged": 0.0,
        "refunded_credit": 0.0,
        "items": [],
    }

    for snapshot in snapshots:
        original_cost = _money(snapshot.original_cost)
        already_refunded = _money(snapshot.refunded_points)
        paid_hours = int(snapshot.paid_hours or (snapshot.billing_period_hours * snapshot.period_count))

        if original_cost <= 0 or paid_hours <= 0:
            snapshot.refund_status = "no_refund"
            snapshot.refunded_at = now
            continue

        used_hours = min(max(_ceil_hours(snapshot.valid_from, now), 1), paid_hours)
        hourly_cost = original_cost / Decimal(paid_hours)
        used_cost = _money(hourly_cost * Decimal(used_hours))

        refundable = original_cost - used_cost - already_refunded
        refund_points = _money(refundable)

        if refund_points <= 0:
            snapshot.refund_status = "no_refund"
            snapshot.refunded_at = now
            snapshot.last_refund_paid_hours = paid_hours
            snapshot.last_refund_used_hours = used_hours
            snapshot.last_refund_used_cost = used_cost
            snapshot.last_refund_points = Decimal("0.00")
            continue

        charged_base = _money(snapshot.charged_consumed)
        credit_base = _money(snapshot.credit_consumed)
        total_base = charged_base + credit_base

        if total_base <= 0:
            snapshot.refund_status = "no_refund"
            snapshot.refunded_at = now
            continue

        refund_charged = _money(refund_points * charged_base / total_base)
        refund_credit = _money(refund_points - refund_charged)

        wallet = await get_or_create_wallet(snapshot.agent_id, db)

        document = await _create_document(
            document_type="delete_refund",
            agent_id=snapshot.agent_id,
            user_id=snapshot.user_id,
            project_id=snapshot.project_id,
            authorization_id=snapshot.authorization_id,
            db=db,
            total_amount=refund_points,
            reason="删除用户自动返点",
        )

        description = (
            f"删除用户返点：用户ID={snapshot.user_id}，项目ID={snapshot.project_id}，"
            f"{LEVEL_NAMES.get(snapshot.user_level, snapshot.user_level)}，"
            f"{snapshot.authorized_devices}台，原扣点{_fmt_money(original_cost)}点，"
            f"购买{paid_hours}小时，已用{used_hours}小时，"
            f"已用点数{_fmt_money(used_cost)}点，"
            f"本次返还{_fmt_money(refund_points)}点。"
            f"规则：不足1小时按1小时计算。"
        )

        if refund_charged > 0:
            before = _money(wallet.charged_balance)
            after = before + refund_charged
            wallet.charged_balance = after

            await _append_ledger_entry(
                db=db,
                wallet=wallet,
                document=document,
                direction="in",
                entry_type="refund",
                balance_type="charged",
                amount=refund_charged,
                balance_before=before,
                balance_after=after,
                business_category="delete_refund",
                business_subtype="refund_charged",
                related_user_id=snapshot.user_id,
                related_project_id=snapshot.project_id,
                related_authorization_id=snapshot.authorization_id,
                related_charge_snapshot_id=snapshot.id,
                description=description,
                source="system",
            )

        if refund_credit > 0:
            before = _money(wallet.credit_balance)
            after = before + refund_credit
            wallet.credit_balance = after

            await _append_ledger_entry(
                db=db,
                wallet=wallet,
                document=document,
                direction="in",
                entry_type="refund",
                balance_type="credit",
                amount=refund_credit,
                balance_before=before,
                balance_after=after,
                business_category="delete_refund",
                business_subtype="refund_credit",
                related_user_id=snapshot.user_id,
                related_project_id=snapshot.project_id,
                related_authorization_id=snapshot.authorization_id,
                related_charge_snapshot_id=snapshot.id,
                description=description,
                source="system",
            )

        snapshot.refunded_points = _money(already_refunded + refund_points)
        snapshot.refunded_charged = _money(snapshot.refunded_charged) + refund_charged
        snapshot.refunded_credit = _money(snapshot.refunded_credit) + refund_credit
        snapshot.refund_status = "refunded"
        snapshot.refunded_at = now
        snapshot.last_refund_paid_hours = paid_hours
        snapshot.last_refund_used_hours = used_hours
        snapshot.last_refund_used_cost = used_cost
        snapshot.last_refund_points = refund_points

        wallet.total_refunded = _money(wallet.total_refunded) + refund_points
        wallet.last_refund_at = now

        summary["refunded_total"] = float(_money(Decimal(str(summary["refunded_total"])) + refund_points))
        summary["refunded_charged"] = float(_money(Decimal(str(summary["refunded_charged"])) + refund_charged))
        summary["refunded_credit"] = float(_money(Decimal(str(summary["refunded_credit"])) + refund_credit))
        summary["items"].append({
            "charge_id": snapshot.id,
            "charge_snapshot_id": snapshot.id,
            "agent_id": snapshot.agent_id,
            "user_id": snapshot.user_id,
            "project_id": snapshot.project_id,
            "original_cost": float(original_cost),
            "paid_hours": paid_hours,
            "used_hours": used_hours,
            "used_cost": float(used_cost),
            "refund_points": float(refund_points),
            "refund_charged": float(refund_charged),
            "refund_credit": float(refund_credit),
        })

    await db.flush()
    return summary


# ─────────────────────────────────────────────────────────────
# 账本查询
# ─────────────────────────────────────────────────────────────

async def get_balance_transactions(
    agent_id: int | None,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    tx_type: str | None = None,
    related_user_id: int | None = None,
    related_project_id: int | None = None,
) -> dict:
    query = select(AccountingLedgerEntry)

    if agent_id is not None:
        query = query.where(AccountingLedgerEntry.agent_id == agent_id)

    if tx_type:
        query = query.where(AccountingLedgerEntry.entry_type == tx_type)

    if related_user_id:
        query = query.where(AccountingLedgerEntry.related_user_id == related_user_id)

    if related_project_id:
        query = query.where(AccountingLedgerEntry.related_project_id == related_project_id)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(AccountingLedgerEntry.posted_at.desc(), AccountingLedgerEntry.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    entries = result.scalars().all()

    agent_ids = {e.agent_id for e in entries}
    user_ids = {e.related_user_id for e in entries if e.related_user_id}
    project_ids = {e.related_project_id for e in entries if e.related_project_id}
    admin_ids = {e.operated_by_admin_id for e in entries if e.operated_by_admin_id}
    charge_ids = {e.related_charge_snapshot_id for e in entries if e.related_charge_snapshot_id}

    agents = {}
    users = {}
    projects = {}
    admins = {}
    charges = {}

    if agent_ids:
        res = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        agents = {a.id: a for a in res.scalars().all()}

    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u for u in res.scalars().all()}

    if project_ids:
        res = await db.execute(select(GameProject).where(GameProject.id.in_(project_ids)))
        projects = {p.id: p for p in res.scalars().all()}

    if admin_ids:
        res = await db.execute(select(Admin).where(Admin.id.in_(admin_ids)))
        admins = {a.id: a for a in res.scalars().all()}

    if charge_ids:
        res = await db.execute(
            select(AuthorizationChargeSnapshot).where(AuthorizationChargeSnapshot.id.in_(charge_ids))
        )
        charges = {c.id: c for c in res.scalars().all()}

    rows = []

    for entry in entries:
        agent = agents.get(entry.agent_id)
        user = users.get(entry.related_user_id)
        project = projects.get(entry.related_project_id)
        admin = admins.get(entry.operated_by_admin_id)
        charge = charges.get(entry.related_charge_snapshot_id)

        authorization_detail = None
        refund_detail = None

        if charge:
            authorization_detail = {
                "charge_id": charge.id,
                "charge_snapshot_id": charge.id,
                "authorization_id": charge.authorization_id,
                "user_level": charge.user_level,
                "level_name": LEVEL_NAMES.get(charge.user_level, charge.user_level),
                "authorized_devices": charge.authorized_devices,
                "billing_period": charge.billing_period,
                "billing_period_hours": charge.billing_period_hours,
                "period_count": charge.period_count,
                "paid_hours": charge.paid_hours,
                "unit_price": float(_money(charge.unit_price)),
                "original_cost": float(_money(charge.original_cost)),
                "charged_consumed": float(_money(charge.charged_consumed)),
                "credit_consumed": float(_money(charge.credit_consumed)),
                "valid_from": charge.valid_from,
                "valid_until": charge.valid_until,
            }

            if entry.entry_type == "refund":
                refund_detail = {
                    "refund_status": charge.refund_status,
                    "refunded_points": float(_money(charge.refunded_points)),
                    "refunded_charged": float(_money(charge.refunded_charged)),
                    "refunded_credit": float(_money(charge.refunded_credit)),
                    "last_refund_paid_hours": charge.last_refund_paid_hours,
                    "last_refund_used_hours": charge.last_refund_used_hours,
                    "last_refund_used_cost": float(_money(charge.last_refund_used_cost)),
                    "last_refund_points": float(_money(charge.last_refund_points)),
                    "refunded_at": charge.refunded_at,
                }

        rows.append({
            "id": entry.id,
            "entry_no": entry.entry_no,

            # 旧字段兼容
            "tx_type": entry.entry_type,
            "tx_type_label": TX_TYPE_LABELS.get(entry.entry_type, entry.entry_type),
            "balance_type": entry.balance_type,
            "balance_type_label": BALANCE_TYPE_LABELS.get(entry.balance_type, entry.balance_type),

            # 新字段
            "direction": entry.direction,
            "entry_type": entry.entry_type,
            "entry_type_label": TX_TYPE_LABELS.get(entry.entry_type, entry.entry_type),
            "business_category": entry.business_category,
            "business_subtype": entry.business_subtype,

            "amount": _signed_amount(entry),
            "raw_amount": float(_money(entry.amount)),
            "balance_before": float(_money(entry.balance_before)),
            "balance_after": float(_money(entry.balance_after)),

            "agent_id": entry.agent_id,
            "agent_username": agent.username if agent else None,

            "operated_by_admin_id": entry.operated_by_admin_id,
            "operated_by_admin_username": admin.username if admin else None,

            "related_user_id": entry.related_user_id,
            "related_user_username": user.username if user else None,

            "related_project_id": entry.related_project_id,
            "related_project_name": project.display_name if project else None,
            "related_project_code": project.code_name if project else None,

            "related_authorization_id": entry.related_authorization_id,
            "related_charge_id": entry.related_charge_snapshot_id,
            "related_charge_snapshot_id": entry.related_charge_snapshot_id,
            "related_document_id": entry.related_document_id,

            "description": entry.description,
            "business_text": entry.business_text or entry.description,
            "authorization_detail": authorization_detail,
            "refund_detail": refund_detail,

            "created_at": entry.posted_at,
            "posted_at": entry.posted_at,
        })

    return {
        "transactions": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ─────────────────────────────────────────────────────────────
# 代理管理聚合
# ─────────────────────────────────────────────────────────────

async def get_agents_with_balance_and_projects(
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: str | None = None,
) -> dict:
    query = select(Agent)

    if status_filter:
        query = query.where(Agent.status == status_filter)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(Agent.level, Agent.id)
        .offset(offset)
        .limit(page_size)
    )
    agents = result.scalars().all()

    agent_ids = [a.id for a in agents]

    wallet_map: dict[int, AccountingWallet] = {}
    auth_map: dict[int, list[dict]] = {aid: [] for aid in agent_ids}

    if agent_ids:
        wallet_result = await db.execute(
            select(AccountingWallet).where(AccountingWallet.agent_id.in_(agent_ids))
        )
        wallet_map = {w.agent_id: w for w in wallet_result.scalars().all()}

        auth_result = await db.execute(
            select(AgentProjectAuth, GameProject)
            .join(GameProject, GameProject.id == AgentProjectAuth.project_id)
            .where(AgentProjectAuth.agent_id.in_(agent_ids))
            .order_by(AgentProjectAuth.id.desc())
        )

        for auth, project in auth_result.all():
            auth_map.setdefault(auth.agent_id, []).append({
                "id": auth.id,
                "project_id": auth.project_id,
                "project_name": project.display_name,
                "project_display_name": project.display_name,
                "project_code": project.code_name,
                "project_code_name": project.code_name,
                "project_type": project.project_type,
                "status": auth.status,
                "valid_until": auth.valid_until,

                # AgentProjectAuth 没有 created_at 字段。
                # 项目授权的业务创建时间应使用 granted_at。
                "created_at": auth.granted_at,
                "granted_at": auth.granted_at,
                "source": auth.source,
                "request_id": auth.request_id,
                "granted_by_admin_id": auth.granted_by_admin_id,
                "granted_reason": auth.granted_reason,
            })

    rows = []

    for agent in agents:
        wallet = wallet_map.get(agent.id)
        if wallet:
            balance = _wallet_response(wallet)
        else:
            balance = {
                "agent_id": agent.id,
                "charged_balance": 0.0,
                "credit_balance": 0.0,
                "frozen_credit": 0.0,
                "available_credit": 0.0,
                "available_total": 0.0,
                "total_recharged": 0.0,
                "total_credited": 0.0,
                "total_consumed": 0.0,
                "total_refunded": 0.0,
                "total_adjusted": 0.0,
                "charged_points": 0.0,
                "credit_points": 0.0,
                "recharge_balance": 0.0,
            }

        rows.append({
            "id": agent.id,
            "username": agent.username,
            "level": agent.level,
            "parent_agent_id": agent.parent_agent_id,
            "created_by_admin_id": agent.created_by_admin_id,
            "commission_rate": float(agent.commission_rate) if agent.commission_rate is not None else None,
            "status": agent.status,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,

            "balance": balance,
            "project_auths": auth_map.get(agent.id, []),
            "authorized_projects": auth_map.get(agent.id, []),

            # 常用余额字段平铺，兼容列表页
            "charged_points": balance["charged_points"],
            "credit_points": balance["credit_points"],
            "frozen_credit": balance["frozen_credit"],
            "available_credit": balance["available_credit"],
            "available_total": balance["available_total"],
            "total_consumed": balance["total_consumed"],
        })

    return {
        "agents": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
