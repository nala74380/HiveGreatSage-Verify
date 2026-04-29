r"""
文件位置: app/services/balance_service.py
名称: 代理余额与项目定价服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.3.0
功能说明:
    项目定价管理、代理余额管理、授权扣点、流水查询。

核心能力:
    - 管理员可查看全局点数流水。
    - 代理可查看自己的余额与流水。
    - 流水返回完整业务上下文：
        管理员给谁充值/授信/冻结/解冻；
        代理给哪个用户授权了什么项目；
        项目内用户等级、单价、授权设备数、到期时间；
        扣点前后余额变化。

计费规则:
    - trial  试用：按周计费，ceil(授权天数 / 7)
    - normal 普通：按月计费，ceil(授权天数 / 30)
    - vip    VIP：按月计费，ceil(授权天数 / 30)
    - svip   SVIP：按月计费，ceil(授权天数 / 30)
    - tester 测试：不进入代理售卖定价体系

点数规则:
    - 点数保留两位小数。
    - 扣点顺序：优先扣充值点数，再扣授信点数。
    - 所有余额变动必须写 balance_transaction。
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
    "trial": {"period": "week", "period_days": 7, "period_name": "周", "unit_label": "每周/台"},
    "normal": {"period": "month", "period_days": 30, "period_name": "月", "unit_label": "每月/台"},
    "vip": {"period": "month", "period_days": 30, "period_name": "月", "unit_label": "每月/台"},
    "svip": {"period": "month", "period_days": 30, "period_name": "月", "unit_label": "每月/台"},
}

TX_TYPE_LABELS = {
    "recharge": "充值",
    "credit": "授信",
    "consume": "消费",
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


def _calc_period_count(user_level: str, start_at: datetime, end_at: datetime) -> int:
    if user_level not in BILLING_RULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户级别 {user_level} 不支持代理计费",
        )

    start_at = _ensure_aware(start_at)
    end_at = _ensure_aware(end_at)

    if end_at <= start_at:
        return 0

    seconds = (end_at - start_at).total_seconds()
    days = max(1, math.ceil(seconds / 86400))
    period_days = BILLING_RULES[user_level]["period_days"]
    return max(1, math.ceil(days / period_days))


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
    unit_price = _money(price.points_per_device)
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
        "unit_label": BILLING_RULES[user_level]["unit_label"],
        "total_cost": float(total_cost),
    }


async def consume_agent_authorization_points(
    *,
    agent_id: int,
    user_id: int,
    project_id: int,
    user_level: str,
    authorized_devices: int,
    start_at: datetime,
    valid_until: datetime,
    db: AsyncSession,
) -> float:
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
        return 0.0

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

    remaining = total_cost
    description = (
        f"用户项目授权扣点：用户ID={user_id}，项目ID={project_id}，"
        f"{cost['level_name']}，{authorized_devices}台，"
        f"单价{_fmt_money(cost['unit_price'])}点/{cost['unit_label']}，"
        f"{cost['period_count']}{cost['billing_period_name']}，"
        f"到期{_fmt_dt(valid_until)}，合计{_fmt_money(total_cost)}点"
    )

    if charged > 0 and remaining > 0:
        consume_charged = min(charged, remaining)
        before = charged
        after = charged - consume_charged
        balance.charged_points = after
        remaining -= consume_charged

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
        ))

    if remaining > 0:
        before = credit
        after = credit - remaining
        balance.credit_points = after

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
        ))

    balance.total_consumed = _money(balance.total_consumed) + total_cost
    await db.flush()

    return float(total_cost)


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

    agent_map: dict[int, Agent] = {}
    admin_map: dict[int, Admin] = {}
    user_map: dict[int, User] = {}
    project_map: dict[int, GameProject] = {}
    auth_map: dict[tuple[int, int], Authorization] = {}
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

    auth_conditions = [
        and_(
            Authorization.user_id == t.related_user_id,
            Authorization.game_project_id == t.related_project_id,
        )
        for t in txs
        if t.related_user_id and t.related_project_id
    ]

    if auth_conditions:
        res = await db.execute(select(Authorization).where(or_(*auth_conditions)))
        for auth in res.scalars().all():
            auth_map[(auth.user_id, auth.game_project_id)] = auth

    price_conditions = []
    for auth in auth_map.values():
        if auth.game_project_id and auth.user_level:
            price_conditions.append(
                and_(
                    ProjectPrice.project_id == auth.game_project_id,
                    ProjectPrice.user_level == auth.user_level,
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

        current_auth = None
        current_price = None

        if tx.related_user_id and tx.related_project_id:
            current_auth = auth_map.get((tx.related_user_id, tx.related_project_id))

        if current_auth:
            current_price = price_map.get((current_auth.game_project_id, current_auth.user_level))

        authorization_detail = None
        if current_auth:
            level = current_auth.user_level
            rule = BILLING_RULES.get(level, {})
            authorization_detail = {
                "authorization_id": current_auth.id,
                "user_level": level,
                "level_name": LEVEL_NAMES.get(level, level),
                "authorized_devices": current_auth.authorized_devices,
                "valid_until": current_auth.valid_until.isoformat() if current_auth.valid_until else None,
                "status": current_auth.status,
                "unit_label": rule.get("unit_label"),
                "billing_period_name": rule.get("period_name"),
                "unit_price": float(_money(current_price.points_per_device)) if current_price else None,
            }

        business_text = _build_transaction_business_text(
            tx=tx,
            agent=agent,
            admin=admin,
            user=user,
            project=project,
            authorization_detail=authorization_detail,
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

            "authorization_detail": authorization_detail,
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

            price_text = f"{_fmt_money(unit_price)}点/{unit_label}" if unit_price is not None else "未取到当前价格"
            expiry_text = valid_until.replace("T", " ")[:19] if valid_until else "永久"

            return (
                f"代理 {agent_name} 给用户 {username} 授权项目「{project_name}」："
                f"{level_name}，{devices} 台，当前价格 {price_text}，"
                f"到期 {expiry_text}，本次扣除 {amount} 点。"
            )

        return tx.description or f"代理 {agent_name} 发生授权扣点 {amount} 点。"

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
        project_map.setdefault(auth.agent_id, []).append({
            "project_id": project.id,
            "code_name": project.code_name,
            "display_name": project.display_name,
            "project_type": project.project_type,
            "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
            "user_count": 0,
        })

    user_count_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id).label("cnt"))
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
        )
        .group_by(User.created_by_agent_id)
    )
    user_count_map = {row[0]: row[1] for row in user_count_result.all()}

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
                "max_users": a.max_users,
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