r"""
文件位置: app/services/balance_service.py
名称: 代理余额与项目定价服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.1.0
功能说明:
    项目定价管理、代理余额管理、授权扣点、流水查询。

计费规则:
    - trial  试用：按周计费，ceil(授权天数 / 7)
    - normal 普通：按月计费，ceil(授权天数 / 30)
    - vip    VIP：按月计费，ceil(授权天数 / 30)
    - svip   SVIP：按月计费，ceil(授权天数 / 30)
    - tester 测试：不进入代理售卖定价体系，不展示、不扣代理点数

点数规则:
    - 点数保留小数点后两位。
    - 扣点顺序：优先 charged_points，不足部分再扣 credit_points - frozen_credit。
    - 所有余额变动必须写 balance_transaction。
"""

import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import (
    Agent,
    AgentBalance,
    AgentProjectAuth,
    Authorization,
    BalanceTransaction,
    GameProject,
    ProjectPrice,
    User,
)


# ── 用户级别与计费周期 ─────────────────────────────────────────

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
        "period_name": "周",
        "unit_label": "每周/台",
    },
    "normal": {
        "period": "month",
        "period_days": 30,
        "period_name": "月",
        "unit_label": "每月/台",
    },
    "vip": {
        "period": "month",
        "period_days": 30,
        "period_name": "月",
        "unit_label": "每月/台",
    },
    "svip": {
        "period": "month",
        "period_days": 30,
        "period_name": "月",
        "unit_label": "每月/台",
    },
}


def _money(value: float | Decimal) -> Decimal:
    """统一保留两位小数。"""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _calc_period_count(user_level: str, start_at: datetime, end_at: datetime) -> int:
    """按用户级别计算计费周期数，至少 1 个周期。"""
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
    """获取项目各级别定价。只返回代理售卖级别，不返回 tester。"""
    result = await db.execute(
        select(ProjectPrice)
        .where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level.in_(PRICING_LEVELS),
        )
        .order_by(ProjectPrice.user_level)
    )
    prices = {p.user_level: p for p in result.scalars().all()}

    return [
        {
            "user_level": level,
            "level_name": LEVEL_NAMES.get(level, level),
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
    """设置或更新某级别单价。"""
    if user_level not in PRICING_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效或不可售卖的用户级别: {user_level}",
        )

    if points_per_device < 0:
        raise HTTPException(status_code=400, detail="点数不能为负数")

    project = await db.get(GameProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    normalized_points = _money(points_per_device)

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()

    if price:
        price.points_per_device = normalized_points
    else:
        price = ProjectPrice(
            project_id=project_id,
            user_level=user_level,
            points_per_device=normalized_points,
        )
        db.add(price)

    await db.flush()

    return {
        "user_level": user_level,
        "level_name": LEVEL_NAMES.get(user_level, user_level),
        "billing_period": BILLING_RULES[user_level]["period"],
        "billing_period_name": BILLING_RULES[user_level]["period_name"],
        "unit_label": BILLING_RULES[user_level]["unit_label"],
        "points_per_device": float(_money(price.points_per_device)),
        "price_id": price.id,
    }


async def delete_project_price(project_id: int, user_level: str, db: AsyncSession) -> None:
    """删除某级别单价。"""
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
    """获取所有项目及其定价，代理项目目录使用。"""
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
    rows = result.all()

    projects: dict[int, dict] = {}

    for project, price in rows:
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
                "level_name": LEVEL_NAMES.get(level, level),
                "billing_period": BILLING_RULES[level]["period"],
                "billing_period_name": BILLING_RULES[level]["period_name"],
                "unit_label": BILLING_RULES[level]["unit_label"],
            }

    return list(projects.values())


# ═══════════════════════════════════════════════════════════════
# 代理余额
# ═══════════════════════════════════════════════════════════════

async def _get_or_create_balance(agent_id: int, db: AsyncSession) -> AgentBalance:
    """获取代理余额记录，不存在则自动创建。"""
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
    """查询代理余额。"""
    balance = await _get_or_create_balance(agent_id, db)

    charged = float(balance.charged_points)
    credit = float(balance.credit_points)
    frozen = float(balance.frozen_credit)
    consumed = float(balance.total_consumed)

    available_credit = credit - frozen
    available_total = charged + available_credit

    return {
        "agent_id": agent_id,

        # 标准字段
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
        description=description or f"管理员充值 {amount_dec} 点",
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
        description=description or f"管理员授信 {amount_dec} 点",
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
        description=description or f"冻结授信 {amount_dec} 点",
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
        description=description or f"解冻授信 {amount_dec} 点",
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
    device_count: int,
    start_at: datetime,
    valid_until: datetime,
    db: AsyncSession,
) -> dict:
    """计算授权扣点，不修改余额。"""
    if user_level not in PRICING_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户级别 {user_level} 不支持代理授权扣点",
        )

    if device_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="代理授权用户时设备数必须大于 0，不能为无限制",
        )

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
            detail=f"该项目尚未设置 {LEVEL_NAMES.get(user_level, user_level)} 级别定价，无法扣点授权",
        )

    period_count = _calc_period_count(user_level, start_at, valid_until)
    unit_price = _money(price.points_per_device)
    total_cost = _money(unit_price * Decimal(device_count) * Decimal(period_count))

    return {
        "project_id": project_id,
        "user_level": user_level,
        "level_name": LEVEL_NAMES.get(user_level, user_level),
        "billing_period": BILLING_RULES[user_level]["period"],
        "billing_period_name": BILLING_RULES[user_level]["period_name"],
        "unit_label": BILLING_RULES[user_level]["unit_label"],
        "unit_price": float(unit_price),
        "device_count": device_count,
        "period_count": period_count,
        "total_cost": float(total_cost),
    }


async def consume_agent_authorization_points(
    *,
    agent_id: int,
    user_id: int,
    project_id: int,
    user_level: str,
    device_count: int,
    start_at: datetime,
    valid_until: datetime,
    db: AsyncSession,
) -> float:
    """
    代理给用户授权项目时扣点。

    扣点失败则抛出 HTTPException，调用方应保持授权不写入。
    """
    cost = await calculate_authorization_cost(
        project_id=project_id,
        user_level=user_level,
        device_count=device_count,
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
            detail=(
                f"代理点数不足：需扣 {total_cost} 点，"
                f"当前可用 {available_total} 点"
            ),
        )

    remaining = total_cost

    # 优先扣充值点数
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
            description=(
                f"用户授权扣点：用户ID={user_id}，项目ID={project_id}，"
                f"{cost['level_name']}，{device_count}台，"
                f"{cost['period_count']}{cost['billing_period_name']}"
            ),
            related_user_id=user_id,
            related_project_id=project_id,
        ))

    # 再扣授信点数
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
            description=(
                f"用户授权扣点：用户ID={user_id}，项目ID={project_id}，"
                f"{cost['level_name']}，{device_count}台，"
                f"{cost['period_count']}{cost['billing_period_name']}"
            ),
            related_user_id=user_id,
            related_project_id=project_id,
        ))

    balance.total_consumed = _money(balance.total_consumed) + total_cost
    await db.flush()

    return float(total_cost)


# ═══════════════════════════════════════════════════════════════
# 查询
# ═══════════════════════════════════════════════════════════════

async def get_balance_transactions(
    agent_id: int,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    tx_type: str | None = None,
) -> dict:
    query = select(BalanceTransaction).where(BalanceTransaction.agent_id == agent_id)
    if tx_type:
        query = query.where(BalanceTransaction.tx_type == tx_type)

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

    tx_type_labels = {
        "recharge": "充值",
        "credit": "授信",
        "consume": "消耗",
        "freeze": "冻结",
        "unfreeze": "解冻",
        "adjust": "调整",
    }

    return {
        "transactions": [
            {
                "id": t.id,
                "tx_type": t.tx_type,
                "tx_type_label": tx_type_labels.get(t.tx_type, t.tx_type),
                "balance_type": t.balance_type,
                "amount": float(t.amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "description": t.description,
                "operated_by_admin_id": t.operated_by_admin_id,
                "related_user_id": t.related_user_id,
                "related_project_id": t.related_project_id,
                "created_at": t.created_at.isoformat(),
            }
            for t in txs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


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

    proj_user_result = await db.execute(
        select(
            User.created_by_agent_id,
            Authorization.game_project_id,
            func.count(func.distinct(User.id)).label("cnt"),
        )
        .join(Authorization, User.id == Authorization.user_id)
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
            Authorization.status == "active",
        )
        .group_by(User.created_by_agent_id, Authorization.game_project_id)
    )
    proj_user_map = {
        (row.created_by_agent_id, row.game_project_id): row.cnt
        for row in proj_user_result.all()
    }

    for agent_id_key, proj_list in project_map.items():
        for p in proj_list:
            p["user_count"] = proj_user_map.get((agent_id_key, p["project_id"]), 0)

    user_count_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id).label("cnt"))
        .where(User.created_by_agent_id.in_(agent_ids), User.is_deleted == False)  # noqa: E712
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