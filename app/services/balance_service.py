r"""
文件位置: app/services/balance_service.py
名称: 代理余额与项目定价服务层
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-04-29
版本: V1.4.2
功能说明:
    项目定价管理、代理余额管理、授权扣点、删除用户返点、流水查询。

核心能力:
    - 管理员可查看全局点数流水。
    - 代理可查看自己的余额与流水。
    - 授权扣点时保存 AuthorizationCharge 快照。
    - 删除用户时按授权扣点快照自动返点。
    - 代理列表增强接口返回：
        代理基础信息；
        用户数量统计；
        点数余额；
        已授权项目；
        每个已授权项目下的直属授权用户数。
    - 流水返回完整业务上下文：
        管理员给谁充值/授信/冻结/解冻；
        代理给哪个用户授权了什么项目；
        项目内用户等级、单价、授权设备数、到期时间；
        删除用户返点的原始扣点、已购买小时、已用小时、已用点数、返还点数；
        扣点/返点前后余额变化。

项目授权用户统计口径:
    authorized_projects[].user_count 表示：
        当前代理直属用户中，拥有该项目 active Authorization 的用户数量。

    不统计下级代理用户。
    下级代理及权限范围统计由代理详情页的 subtree 统计承担。

计费规则:
    - trial  试用：按周计费，1 周 = 168 小时。
    - normal 普通：按月计费，1 月 = 720 小时。
    - vip    VIP：按月计费，1 月 = 720 小时。
    - svip   SVIP：按月计费，1 月 = 720 小时。
    - tester 测试：不进入代理售卖定价体系。

返点规则:
    - 不足 1 小时按 1 小时扣费。
    - 每小时成本 = 原始扣点 / 已购买总小时数。
    - 返点 = 原始扣点 - 每小时成本 × 已使用小时数 - 已返还点数。
    - 已过期授权不返点。
    - 管理员免费授权不返点。
    - 返点按原扣点来源比例返还到充值点数 / 授信点数。
"""

import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import (
    Admin,
    Agent,
    AgentBalance,
    AgentProjectAuth,
    Authorization,
    AuthorizationCharge,
    BalanceTransaction,
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
    "consume": "消费",
    "refund": "返点",
    "freeze": "冻结",
    "unfreeze": "解冻",
    "adjust": "调整",
}

BALANCE_TYPE_LABELS = {
    "charged": "充值点数",
    "credit": "授信点数",
}


def _money(value: float | Decimal | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt_money(value: float | Decimal | int | None) -> str:
    return f"{float(_money(value)):.2f}"


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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


# ═══════════════════════════════════════════════════════════════
# 项目定价
# ═══════════════════════════════════════════════════════════════

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
        raise HTTPException(status_code=400, detail=f"不可售卖用户级别: {user_level}")

    if points_per_device < 0:
        raise HTTPException(status_code=400, detail="点数不能为负数")

    project = await db.get(GameProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
        raise HTTPException(status_code=404, detail="定价记录不存在")

    await db.delete(price)
    await db.flush()


async def get_all_projects_with_prices(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(GameProject, ProjectPrice)
        .outerjoin(
            ProjectPrice,
            (GameProject.id == ProjectPrice.project_id)
            & (ProjectPrice.user_level.in_(PRICING_LEVELS)),
        )
        .where(GameProject.is_active == True)  # noqa: E712
        .order_by(GameProject.id, ProjectPrice.user_level)
    )

    projects: dict[int, dict] = {}

    for project, price in result.all():
        if project.id not in projects:
            projects[project.id] = {
                "id": project.id,
                "code_name": project.code_name,
                "display_name": project.display_name,
                "project_type": project.project_type,
                "project_uuid": str(project.project_uuid),
                "prices": {},
                "price_meta": {},
            }

        if price:
            level = price.user_level
            projects[project.id]["prices"][level] = float(_money(price.points_per_device))
            projects[project.id]["price_meta"][level] = {
                "level_name": LEVEL_NAMES[level],
                "billing_period": BILLING_RULES[level]["period"],
                "billing_period_name": BILLING_RULES[level]["period_name"],
                "billing_period_hours": BILLING_RULES[level]["period_hours"],
                "unit_label": BILLING_RULES[level]["unit_label"],
            }

    return list(projects.values())


# ═══════════════════════════════════════════════════════════════
# 代理余额
# ═══════════════════════════════════════════════════════════════

async def _get_or_create_balance(agent_id: int, db: AsyncSession) -> AgentBalance:
    result = await db.execute(
        select(AgentBalance).where(AgentBalance.agent_id == agent_id)
    )
    balance = result.scalar_one_or_none()

    if not balance:
        balance = AgentBalance(agent_id=agent_id)
        db.add(balance)
        await db.flush()

    return balance


async def get_agent_balance(agent_id: int, db: AsyncSession) -> dict:
    balance = await _get_or_create_balance(agent_id, db)

    charged = float(balance.charged_points)
    credit = float(balance.credit_points)
    frozen = float(balance.frozen_credit)
    consumed = float(balance.total_consumed)

    available_credit = credit - frozen
    available_total = charged + available_credit

    return {
        "agent_id": agent_id,
        "charged_points": charged,
        "credit_points": credit,
        "frozen_credit": frozen,
        "available_credit": available_credit,
        "available_total": available_total,
        "total_consumed": consumed,

        # 前端兼容字段
        "recharge_balance": charged,
        "credit_balance": available_credit,
    }


async def recharge_agent(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于 0")

    amount_dec = _money(amount)
    balance = await _get_or_create_balance(agent_id, db)

    before = _money(balance.charged_points)
    after = before + amount_dec
    balance.charged_points = after

    tx = BalanceTransaction(
        agent_id=agent_id,
        tx_type="recharge",
        balance_type="charged",
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        description=description or f"管理员充值 {_fmt_money(amount_dec)} 点",
        operated_by_admin_id=admin_id,
    )
    db.add(tx)
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
        raise HTTPException(status_code=400, detail="授信金额必须大于 0")

    amount_dec = _money(amount)
    balance = await _get_or_create_balance(agent_id, db)

    before = _money(balance.credit_points)
    after = before + amount_dec
    balance.credit_points = after

    tx = BalanceTransaction(
        agent_id=agent_id,
        tx_type="credit",
        balance_type="credit",
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        description=description or f"管理员授信 {_fmt_money(amount_dec)} 点",
        operated_by_admin_id=admin_id,
    )
    db.add(tx)
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
        raise HTTPException(status_code=400, detail="冻结金额必须大于 0")

    amount_dec = _money(amount)
    balance = await _get_or_create_balance(agent_id, db)

    available_credit = _money(balance.credit_points) - _money(balance.frozen_credit)
    if amount_dec > available_credit:
        raise HTTPException(
            status_code=400,
            detail=f"可冻结授信不足（可用授信: {available_credit} 点，请求冻结: {amount_dec} 点）",
        )

    before = _money(balance.frozen_credit)
    after = before + amount_dec
    balance.frozen_credit = after

    tx = BalanceTransaction(
        agent_id=agent_id,
        tx_type="freeze",
        balance_type="credit",
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        description=description or f"冻结授信 {_fmt_money(amount_dec)} 点",
        operated_by_admin_id=admin_id,
    )
    db.add(tx)
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
        raise HTTPException(status_code=400, detail="解冻金额必须大于 0")

    amount_dec = _money(amount)
    balance = await _get_or_create_balance(agent_id, db)

    frozen = _money(balance.frozen_credit)
    if amount_dec > frozen:
        raise HTTPException(
            status_code=400,
            detail=f"已冻结金额不足（已冻结: {frozen} 点，请求解冻: {amount_dec} 点）",
        )

    before = frozen
    after = before - amount_dec
    balance.frozen_credit = after

    tx = BalanceTransaction(
        agent_id=agent_id,
        tx_type="unfreeze",
        balance_type="credit",
        amount=-amount_dec,
        balance_before=before,
        balance_after=after,
        description=description or f"解冻授信 {_fmt_money(amount_dec)} 点",
        operated_by_admin_id=admin_id,
    )
    db.add(tx)
    await db.flush()

    return await get_agent_balance(agent_id, db)


# ═══════════════════════════════════════════════════════════════
# 授权扣点
# ═══════════════════════════════════════════════════════════════

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
        raise HTTPException(status_code=400, detail=f"用户级别 {user_level} 不支持代理计费")

    if authorized_devices <= 0:
        raise HTTPException(status_code=400, detail="代理授权设备数必须大于 0")

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()
    if not price:
        raise HTTPException(
            status_code=400,
            detail=f"该项目尚未设置 {LEVEL_NAMES.get(user_level, user_level)} 级别定价",
        )

    period_count = _calc_period_count(user_level, start_at, valid_until)
    if period_count <= 0:
        raise HTTPException(status_code=400, detail="授权到期时间必须晚于授权开始时间")

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
    """
    代理授权扣点，并保存 AuthorizationCharge 快照。

    注意:
        - 必须在 Authorization 已经 flush 取得 ID 后调用。
        - 本函数会创建 consume 流水。
        - 本函数会保存扣点来源 charged/credit，用于后续删除用户返点。
    """
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
        }

    balance = await _get_or_create_balance(agent_id, db)

    charged = _money(balance.charged_points)
    credit = _money(balance.credit_points)
    frozen = _money(balance.frozen_credit)
    available_credit = credit - frozen
    available_total = charged + available_credit

    if total_cost > available_total:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"代理点数不足：需扣 {total_cost} 点，当前可用 {available_total} 点",
        )

    charge = AuthorizationCharge(
        authorization_id=authorization_id,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        user_level=user_level,
        unit_price=_money(cost["unit_price"]),
        authorized_devices=authorized_devices,
        billing_period=cost["billing_period"],
        billing_period_hours=cost["billing_period_hours"],
        period_count=cost["period_count"],
        paid_hours=cost["paid_hours"],
        valid_from=_ensure_aware(start_at),
        valid_until=_ensure_aware(valid_until),
        original_cost=total_cost,
        charged_consumed=Decimal("0.00"),
        credit_consumed=Decimal("0.00"),
        refunded_points=Decimal("0.00"),
        refund_status="none",
    )
    db.add(charge)
    await db.flush()

    remaining = total_cost
    charged_consumed = Decimal("0.00")
    credit_consumed = Decimal("0.00")

    description = (
        f"用户项目授权扣点：用户ID={user_id}，项目ID={project_id}，"
        f"{cost['level_name']}，{authorized_devices}台，"
        f"单价{_fmt_money(cost['unit_price'])}点/{cost['unit_label']}，"
        f"{cost['period_count']}{cost['billing_period_name']}，"
        f"购买{cost['paid_hours']}小时，到期{_fmt_dt(valid_until)}，"
        f"合计{_fmt_money(total_cost)}点"
    )

    if charged > 0 and remaining > 0:
        consume_charged = min(charged, remaining)
        before = charged
        after = charged - consume_charged
        balance.charged_points = after
        remaining -= consume_charged
        charged_consumed = consume_charged

        db.add(BalanceTransaction(
            agent_id=agent_id,
            tx_type="consume",
            balance_type="charged",
            amount=-consume_charged,
            balance_before=before,
            balance_after=after,
            description=description,
            related_user_id=user_id,
            related_project_id=project_id,
            related_charge_id=charge.id,
        ))

    if remaining > 0:
        before = credit
        after = credit - remaining
        balance.credit_points = after
        credit_consumed = remaining

        db.add(BalanceTransaction(
            agent_id=agent_id,
            tx_type="consume",
            balance_type="credit",
            amount=-remaining,
            balance_before=before,
            balance_after=after,
            description=description,
            related_user_id=user_id,
            related_project_id=project_id,
            related_charge_id=charge.id,
        ))

    charge.charged_consumed = _money(charged_consumed)
    charge.credit_consumed = _money(credit_consumed)

    balance.total_consumed = _money(balance.total_consumed) + total_cost
    await db.flush()

    return {
        "total_cost": float(total_cost),
        "charge_id": charge.id,
        "charged_consumed": float(_money(charged_consumed)),
        "credit_consumed": float(_money(credit_consumed)),
    }


# ═══════════════════════════════════════════════════════════════
# 删除用户返点
# ═══════════════════════════════════════════════════════════════

async def refund_user_authorization_points_on_delete(
    *,
    user_id: int,
    db: AsyncSession,
    delete_time: datetime | None = None,
) -> dict:
    """
    删除用户时，按授权扣点快照自动返点。

    规则:
        - 只处理存在 AuthorizationCharge 的代理扣点授权。
        - valid_until <= delete_time 的已过期授权不返点。
        - 不足 1 小时按 1 小时扣费。
        - 返点按原扣点来源比例返还到 charged / credit。
    """
    now = _ensure_aware(delete_time or datetime.now(timezone.utc))

    result = await db.execute(
        select(AuthorizationCharge).where(
            AuthorizationCharge.user_id == user_id,
            AuthorizationCharge.refund_status == "none",
            AuthorizationCharge.valid_until > now,
        )
        .order_by(AuthorizationCharge.id.asc())
    )
    charges = result.scalars().all()

    summary = {
        "user_id": user_id,
        "refunded_total": 0.0,
        "refunded_charged": 0.0,
        "refunded_credit": 0.0,
        "items": [],
    }

    for charge in charges:
        original_cost = _money(charge.original_cost)
        already_refunded = _money(charge.refunded_points)
        paid_hours = int(charge.paid_hours or (charge.billing_period_hours * charge.period_count))

        if original_cost <= 0 or paid_hours <= 0:
            charge.refund_status = "no_refund"
            charge.refunded_at = now
            continue

        raw_used_hours = _ceil_hours(charge.valid_from, now)
        used_hours = min(max(raw_used_hours, 1), paid_hours)

        hourly_cost = original_cost / Decimal(paid_hours)
        used_cost = _money(hourly_cost * Decimal(used_hours))

        refundable = original_cost - used_cost - already_refunded
        refund_points = _money(refundable)

        if refund_points <= 0:
            charge.refund_status = "no_refund"
            charge.refunded_at = now
            charge.last_refund_paid_hours = paid_hours
            charge.last_refund_used_hours = used_hours
            charge.last_refund_used_cost = used_cost
            charge.last_refund_points = Decimal("0.00")
            continue

        charged_base = _money(charge.charged_consumed)
        credit_base = _money(charge.credit_consumed)
        total_base = charged_base + credit_base

        if total_base <= 0:
            charge.refund_status = "no_refund"
            charge.refunded_at = now
            continue

        refund_charged = _money(refund_points * charged_base / total_base)
        refund_credit = _money(refund_points - refund_charged)

        balance = await _get_or_create_balance(charge.agent_id, db)

        description = (
            f"删除用户返点：用户ID={charge.user_id}，项目ID={charge.project_id}，"
            f"{LEVEL_NAMES.get(charge.user_level, charge.user_level)}，"
            f"{charge.authorized_devices}台，原扣点{_fmt_money(original_cost)}点，"
            f"购买{paid_hours}小时，已用{used_hours}小时，"
            f"已用点数{_fmt_money(used_cost)}点，"
            f"本次返还{_fmt_money(refund_points)}点。"
            f"规则：不足1小时按1小时计算。"
        )

        if refund_charged > 0:
            before = _money(balance.charged_points)
            after = before + refund_charged
            balance.charged_points = after

            db.add(BalanceTransaction(
                agent_id=charge.agent_id,
                tx_type="refund",
                balance_type="charged",
                amount=refund_charged,
                balance_before=before,
                balance_after=after,
                description=description,
                related_user_id=charge.user_id,
                related_project_id=charge.project_id,
                related_charge_id=charge.id,
            ))

        if refund_credit > 0:
            before = _money(balance.credit_points)
            after = before + refund_credit
            balance.credit_points = after

            db.add(BalanceTransaction(
                agent_id=charge.agent_id,
                tx_type="refund",
                balance_type="credit",
                amount=refund_credit,
                balance_before=before,
                balance_after=after,
                description=description,
                related_user_id=charge.user_id,
                related_project_id=charge.project_id,
                related_charge_id=charge.id,
            ))

        charge.refunded_points = _money(already_refunded + refund_points)
        charge.refund_status = "refunded"
        charge.refunded_at = now
        charge.last_refund_paid_hours = paid_hours
        charge.last_refund_used_hours = used_hours
        charge.last_refund_used_cost = used_cost
        charge.last_refund_points = refund_points

        summary["refunded_total"] = float(_money(Decimal(str(summary["refunded_total"])) + refund_points))
        summary["refunded_charged"] = float(_money(Decimal(str(summary["refunded_charged"])) + refund_charged))
        summary["refunded_credit"] = float(_money(Decimal(str(summary["refunded_credit"])) + refund_credit))
        summary["items"].append({
            "charge_id": charge.id,
            "agent_id": charge.agent_id,
            "user_id": charge.user_id,
            "project_id": charge.project_id,
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


# ═══════════════════════════════════════════════════════════════
# 点数流水查询
# ═══════════════════════════════════════════════════════════════

async def get_balance_transactions(
    agent_id: int | None,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    tx_type: str | None = None,
    related_user_id: int | None = None,
    related_project_id: int | None = None,
) -> dict:
    """
    查询点数流水。

    - agent_id=None：管理员全局流水。
    - agent_id=具体ID：代理自身或管理员查看某代理流水。
    """
    query = select(BalanceTransaction)

    if agent_id is not None:
        query = query.where(BalanceTransaction.agent_id == agent_id)

    if tx_type:
        query = query.where(BalanceTransaction.tx_type == tx_type)

    if related_user_id:
        query = query.where(BalanceTransaction.related_user_id == related_user_id)

    if related_project_id:
        query = query.where(BalanceTransaction.related_project_id == related_project_id)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(BalanceTransaction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    txs = result.scalars().all()

    enriched = await _enrich_transactions(txs, db)

    return {
        "transactions": enriched,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _enrich_transactions(txs: list[BalanceTransaction], db: AsyncSession) -> list[dict]:
    if not txs:
        return []

    agent_ids = sorted({t.agent_id for t in txs if t.agent_id})
    admin_ids = sorted({t.operated_by_admin_id for t in txs if t.operated_by_admin_id})
    user_ids = sorted({t.related_user_id for t in txs if t.related_user_id})
    project_ids = sorted({t.related_project_id for t in txs if t.related_project_id})
    charge_ids = sorted({t.related_charge_id for t in txs if t.related_charge_id})

    agent_map: dict[int, Agent] = {}
    admin_map: dict[int, Admin] = {}
    user_map: dict[int, User] = {}
    project_map: dict[int, GameProject] = {}
    charge_map: dict[int, AuthorizationCharge] = {}
    price_map: dict[tuple[int, str], ProjectPrice] = {}

    if agent_ids:
        res = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        agent_map = {a.id: a for a in res.scalars().all()}

    if admin_ids:
        res = await db.execute(select(Admin).where(Admin.id.in_(admin_ids)))
        admin_map = {a.id: a for a in res.scalars().all()}

    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        user_map = {u.id: u for u in res.scalars().all()}

    if project_ids:
        res = await db.execute(select(GameProject).where(GameProject.id.in_(project_ids)))
        project_map = {p.id: p for p in res.scalars().all()}

    if charge_ids:
        res = await db.execute(
            select(AuthorizationCharge).where(AuthorizationCharge.id.in_(charge_ids))
        )
        charge_map = {c.id: c for c in res.scalars().all()}

    price_conditions = []
    for charge in charge_map.values():
        price_conditions.append(
            and_(
                ProjectPrice.project_id == charge.project_id,
                ProjectPrice.user_level == charge.user_level,
            )
        )

    if price_conditions:
        res = await db.execute(select(ProjectPrice).where(or_(*price_conditions)))
        for price in res.scalars().all():
            price_map[(price.project_id, price.user_level)] = price

    rows: list[dict] = []

    for tx in txs:
        agent = agent_map.get(tx.agent_id)
        admin = admin_map.get(tx.operated_by_admin_id) if tx.operated_by_admin_id else None
        user = user_map.get(tx.related_user_id) if tx.related_user_id else None
        project = project_map.get(tx.related_project_id) if tx.related_project_id else None
        charge = charge_map.get(tx.related_charge_id) if tx.related_charge_id else None

        authorization_detail = None
        refund_detail = None

        if charge:
            level = charge.user_level
            rule = BILLING_RULES.get(level, {})
            current_price = price_map.get((charge.project_id, charge.user_level))

            authorization_detail = {
                "authorization_id": charge.authorization_id,
                "charge_id": charge.id,
                "user_level": level,
                "level_name": LEVEL_NAMES.get(level, level),
                "authorized_devices": charge.authorized_devices,
                "valid_from": charge.valid_from.isoformat() if charge.valid_from else None,
                "valid_until": charge.valid_until.isoformat() if charge.valid_until else None,
                "unit_label": rule.get("unit_label"),
                "billing_period": charge.billing_period,
                "billing_period_name": rule.get("period_name"),
                "billing_period_hours": charge.billing_period_hours,
                "period_count": charge.period_count,
                "paid_hours": charge.paid_hours,
                "unit_price": float(_money(charge.unit_price)),
                "current_unit_price": float(_money(current_price.points_per_device)) if current_price else None,
                "original_cost": float(_money(charge.original_cost)),
            }

            if tx.tx_type == "refund":
                refund_detail = {
                    "charge_id": charge.id,
                    "original_cost": float(_money(charge.original_cost)),
                    "paid_hours": charge.last_refund_paid_hours or charge.paid_hours,
                    "used_hours": charge.last_refund_used_hours,
                    "used_cost": float(_money(charge.last_refund_used_cost)),
                    "refund_points": float(_money(charge.last_refund_points)),
                    "refunded_points": float(_money(charge.refunded_points)),
                    "refund_status": charge.refund_status,
                    "rule_text": "不足1小时按1小时计算；返点 = 原始扣点 - 每小时成本 × 已使用小时数 - 已返还点数。",
                }

        business_text = _build_transaction_business_text(
            tx=tx,
            agent=agent,
            admin=admin,
            user=user,
            project=project,
            authorization_detail=authorization_detail,
            refund_detail=refund_detail,
        )

        rows.append({
            "id": tx.id,
            "tx_type": tx.tx_type,
            "tx_type_label": TX_TYPE_LABELS.get(tx.tx_type, tx.tx_type),
            "balance_type": tx.balance_type,
            "balance_type_label": BALANCE_TYPE_LABELS.get(tx.balance_type, tx.balance_type),
            "amount": float(tx.amount),
            "amount_text": _fmt_money(tx.amount),
            "balance_before": float(tx.balance_before),
            "balance_after": float(tx.balance_after),
            "balance_before_text": _fmt_money(tx.balance_before),
            "balance_after_text": _fmt_money(tx.balance_after),
            "description": tx.description,

            "agent_id": tx.agent_id,
            "agent_username": agent.username if agent else None,

            "operated_by_admin_id": tx.operated_by_admin_id,
            "operated_by_admin_username": admin.username if admin else None,

            "related_user_id": tx.related_user_id,
            "related_username": user.username if user else None,

            "related_project_id": tx.related_project_id,
            "related_project_name": project.display_name if project else None,
            "related_project_code": project.code_name if project else None,

            "related_charge_id": tx.related_charge_id,
            "authorization_detail": authorization_detail,
            "refund_detail": refund_detail,
            "business_text": business_text,

            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })

    return rows


def _build_transaction_business_text(
    *,
    tx: BalanceTransaction,
    agent: Agent | None,
    admin: Admin | None,
    user: User | None,
    project: GameProject | None,
    authorization_detail: dict | None,
    refund_detail: dict | None,
) -> str:
    agent_name = agent.username if agent else f"代理ID={tx.agent_id}"
    admin_name = admin.username if admin else (f"管理员ID={tx.operated_by_admin_id}" if tx.operated_by_admin_id else "系统")
    amount = _fmt_money(abs(tx.amount))

    if tx.tx_type == "recharge":
        return f"{admin_name} 给代理 {agent_name} 充值 {amount} 点。"

    if tx.tx_type == "credit":
        return f"{admin_name} 给代理 {agent_name} 授信 {amount} 点。"

    if tx.tx_type == "freeze":
        return f"{admin_name} 冻结代理 {agent_name} 授信 {amount} 点。"

    if tx.tx_type == "unfreeze":
        return f"{admin_name} 解冻代理 {agent_name} 授信 {amount} 点。"

    if tx.tx_type == "consume":
        username = user.username if user else f"用户ID={tx.related_user_id}"
        project_name = project.display_name if project else f"项目ID={tx.related_project_id}"

        if authorization_detail:
            level_name = authorization_detail.get("level_name") or authorization_detail.get("user_level")
            devices = authorization_detail.get("authorized_devices")
            valid_until = authorization_detail.get("valid_until")
            unit_price = authorization_detail.get("unit_price")
            unit_label = authorization_detail.get("unit_label") or "周期/台"
            paid_hours = authorization_detail.get("paid_hours")
            original_cost = authorization_detail.get("original_cost")

            price_text = f"{_fmt_money(unit_price)}点/{unit_label}" if unit_price is not None else "未取到授权快照价格"
            expiry_text = valid_until.replace("T", " ")[:19] if valid_until else "永久"

            return (
                f"代理 {agent_name} 给用户 {username} 授权项目「{project_name}」："
                f"{level_name}，{devices} 台，授权快照价格 {price_text}，"
                f"购买 {paid_hours} 小时，到期 {expiry_text}，"
                f"本次扣除 {amount} 点，原始应扣 {_fmt_money(original_cost)} 点。"
            )

        return tx.description or f"代理 {agent_name} 发生授权扣点 {amount} 点。"

    if tx.tx_type == "refund":
        username = user.username if user else f"用户ID={tx.related_user_id}"
        project_name = project.display_name if project else f"项目ID={tx.related_project_id}"

        if refund_detail and authorization_detail:
            level_name = authorization_detail.get("level_name")
            devices = authorization_detail.get("authorized_devices")
            original_cost = refund_detail.get("original_cost")
            paid_hours = refund_detail.get("paid_hours")
            used_hours = refund_detail.get("used_hours")
            used_cost = refund_detail.get("used_cost")
            refund_points = refund_detail.get("refund_points")

            return (
                f"删除用户返点：代理 {agent_name} 的用户 {username}，项目「{project_name}」，"
                f"{level_name}，{devices} 台。"
                f"原扣点 {_fmt_money(original_cost)} 点，购买 {paid_hours} 小时，"
                f"已使用 {used_hours} 小时，已用点数 {_fmt_money(used_cost)} 点，"
                f"本次返还 {_fmt_money(refund_points)} 点。"
                f"规则：不足 1 小时按 1 小时计算。"
            )

        return tx.description or f"删除用户返点 {amount} 点。"

    return tx.description or f"{TX_TYPE_LABELS.get(tx.tx_type, tx.tx_type)} {amount} 点。"


# ═══════════════════════════════════════════════════════════════
# 代理列表增强
# ═══════════════════════════════════════════════════════════════

async def get_agents_with_balance_and_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> dict:
    """
    管理端代理增强列表。

    返回:
        - 代理基础信息
        - 直属用户数
        - 点数余额
        - 已授权项目
        - 每个已授权项目下的直属授权用户数

    authorized_projects[].user_count 口径:
        当前代理直属用户中，拥有该项目 active Authorization 的用户数量。
    """
    query = select(Agent)

    if status_filter:
        query = query.where(Agent.status == status_filter)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Agent.id.desc()).offset(offset).limit(page_size)
    )
    agents = result.scalars().all()

    if not agents:
        return {"agents": [], "total": total, "page": page, "page_size": page_size}

    agent_ids = [a.id for a in agents]

    bal_result = await db.execute(
        select(AgentBalance).where(AgentBalance.agent_id.in_(agent_ids))
    )
    balance_map = {b.agent_id: b for b in bal_result.scalars().all()}

    user_count_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id).label("cnt"))
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
        )
        .group_by(User.created_by_agent_id)
    )
    user_count_map = {row[0]: row[1] for row in user_count_result.all()}

    project_user_count_result = await db.execute(
        select(
            User.created_by_agent_id.label("agent_id"),
            Authorization.game_project_id.label("project_id"),
            func.count(func.distinct(User.id)).label("cnt"),
        )
        .join(Authorization, Authorization.user_id == User.id)
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
            Authorization.status == "active",
        )
        .group_by(User.created_by_agent_id, Authorization.game_project_id)
    )

    project_user_count_map = {
        (row.agent_id, row.project_id): row.cnt
        for row in project_user_count_result.all()
    }

    auth_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id.in_(agent_ids),
            AgentProjectAuth.status == "active",
        )
    )

    project_map: dict[int, list[dict]] = {}
    for auth, project in auth_result.all():
        user_count = project_user_count_map.get((auth.agent_id, project.id), 0)

        project_map.setdefault(auth.agent_id, []).append({
            "project_id": project.id,
            "code_name": project.code_name,
            "display_name": project.display_name,
            "project_type": project.project_type,
            "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
            "user_count": user_count,
        })

    def _fmt_balance(b: AgentBalance | None) -> dict:
        if not b:
            return {
                "charged_points": 0.0,
                "credit_points": 0.0,
                "frozen_credit": 0.0,
                "available_total": 0.0,
            }
        return {
            "charged_points": float(b.charged_points),
            "credit_points": float(b.credit_points),
            "frozen_credit": float(b.frozen_credit),
            "available_total": (
                float(b.charged_points)
                + float(b.credit_points)
                - float(b.frozen_credit)
            ),
        }

    return {
        "agents": [
            {
                "id": a.id,
                "username": a.username,
                "level": a.level,
                "status": a.status,
                "users_count": user_count_map.get(a.id, 0),
                "commission_rate": float(a.commission_rate) if a.commission_rate else None,
                "created_at": a.created_at.isoformat(),
                "authorized_projects": project_map.get(a.id, []),
                "balance": _fmt_balance(balance_map.get(a.id)),
            }
            for a in agents
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }