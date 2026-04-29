r"""
文件位置: app/services/balance_service.py
名称: 代理余额与项目定价服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.0.0
功能说明:
    项目定价管理（CRUD）、代理余额管理（充值/授信/冻结/消耗）、流水查询。

    点数使用顺序：优先扣 charged_points，不足再扣 credit_points - frozen_credit。
    冻结操作：将 credit_points 中指定金额移到 frozen_credit，不可使用但不消失。
    所有变动必须写 balance_transaction 流水记录。
"""

import logging
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import (
    Agent, AgentBalance, AgentProjectAuth, BalanceTransaction,
    GameProject, ProjectPrice, User, Authorization
)

logger = logging.getLogger(__name__)

# ── 用户级别显示名 ─────────────────────────────────────────────
LEVEL_NAMES = {
    "trial":  "试用",
    "normal": "普通",
    "vip":    "VIP",
    "svip":   "SVIP",
    "tester": "测试",
}
ALL_LEVELS = list(LEVEL_NAMES.keys())


# ═══════════════════════════════════════════════════════════════
# 项目定价
# ═══════════════════════════════════════════════════════════════

async def get_project_prices(project_id: int, db: AsyncSession) -> list[dict]:
    """获取项目所有级别的定价。没有定价的级别返回 None。"""
    result = await db.execute(
        select(ProjectPrice).where(ProjectPrice.project_id == project_id)
        .order_by(ProjectPrice.user_level)
    )
    prices = {p.user_level: p for p in result.scalars().all()}
    return [
        {
            "user_level":        level,
            "level_name":        LEVEL_NAMES.get(level, level),
            "points_per_device": float(prices[level].points_per_device) if level in prices else None,
            "price_id":          prices[level].id if level in prices else None,
        }
        for level in ALL_LEVELS
    ]


async def set_project_price(
    project_id: int,
    user_level: str,
    points_per_device: float,
    db: AsyncSession,
) -> dict:
    """设置或更新某级别的单价（UPSERT）。"""
    if user_level not in ALL_LEVELS:
        raise HTTPException(status_code=400, detail=f"无效的用户级别: {user_level}")
    if points_per_device < 0:
        raise HTTPException(status_code=400, detail="点数不能为负数")

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == project_id,
            ProjectPrice.user_level == user_level,
        )
    )
    price = result.scalar_one_or_none()
    if price:
        price.points_per_device = Decimal(str(points_per_device))
    else:
        project = await db.get(GameProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        price = ProjectPrice(
            project_id=project_id,
            user_level=user_level,
            points_per_device=Decimal(str(points_per_device)),
        )
        db.add(price)
    await db.flush()
    return {
        "user_level":        user_level,
        "level_name":        LEVEL_NAMES.get(user_level, user_level),
        "points_per_device": float(price.points_per_device),
        "price_id":          price.id,
    }


async def delete_project_price(project_id: int, user_level: str, db: AsyncSession) -> None:
    """删除某级别的单价（不再收费）。"""
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
    """获取所有项目及其定价（代理查看价格目录用）。"""
    result = await db.execute(
        select(GameProject, ProjectPrice)
        .outerjoin(ProjectPrice, GameProject.id == ProjectPrice.project_id)
        .where(GameProject.is_active == True)
        .order_by(GameProject.id, ProjectPrice.user_level)
    )
    rows = result.all()

    projects: dict[int, dict] = {}
    for project, price in rows:
        if project.id not in projects:
            projects[project.id] = {
                "id":           project.id,
                "code_name":    project.code_name,
                "display_name": project.display_name,
                "project_type": project.project_type,
                "project_uuid": str(project.project_uuid),
                "prices":       {},
            }
        if price:
            projects[project.id]["prices"][price.user_level] = float(price.points_per_device)

    return list(projects.values())


# ═══════════════════════════════════════════════════════════════
# 代理余额
# ═══════════════════════════════════════════════════════════════

async def _get_or_create_balance(agent_id: int, db: AsyncSession) -> AgentBalance:
    """获取代理余额记录，不存在则自动创建（初始全为 0）。"""
    balance = await db.get(AgentBalance, agent_id)
    if not balance:
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
    """查询代理余额（含可用余额计算）。"""
    balance = await _get_or_create_balance(agent_id, db)
    charged  = float(balance.charged_points)
    credit   = float(balance.credit_points)
    frozen   = float(balance.frozen_credit)
    consumed = float(balance.total_consumed)
    return {
        "agent_id":         agent_id,
        "charged_points":   charged,
        "credit_points":    credit,
        "frozen_credit":    frozen,
        "available_credit": credit - frozen,
        "available_total":  charged + (credit - frozen),
        "total_consumed":   consumed,
    }


async def recharge_agent(
    agent_id: int,
    amount: float,
    description: str | None,
    admin_id: int,
    db: AsyncSession,
) -> dict:
    """管理员给代理充值点数（增加 charged_points）。"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于 0")
    balance = await _get_or_create_balance(agent_id, db)
    before  = float(balance.charged_points)
    after   = before + amount
    balance.charged_points = Decimal(str(after))
    tx = BalanceTransaction(
        agent_id=agent_id, tx_type="recharge", balance_type="charged",
        amount=Decimal(str(amount)), balance_before=Decimal(str(before)),
        balance_after=Decimal(str(after)),
        description=description or f"管理员充值 {amount} 点",
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
    """管理员给代理授信点数（增加 credit_points）。"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="授信金额必须大于 0")
    balance = await _get_or_create_balance(agent_id, db)
    before  = float(balance.credit_points)
    after   = before + amount
    balance.credit_points = Decimal(str(after))
    tx = BalanceTransaction(
        agent_id=agent_id, tx_type="credit", balance_type="credit",
        amount=Decimal(str(amount)), balance_before=Decimal(str(before)),
        balance_after=Decimal(str(after)),
        description=description or f"管理员授信 {amount} 点",
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
    """冻结代理的授信点数（不能超过可用授信）。"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="冻结金额必须大于 0")
    balance = await _get_or_create_balance(agent_id, db)
    available_credit = float(balance.credit_points) - float(balance.frozen_credit)
    if amount > available_credit:
        raise HTTPException(
            status_code=400,
            detail=f"可冻结授信不足（可用授信: {available_credit:.4f} 点，请求冻结: {amount:.4f} 点）",
        )
    before = float(balance.frozen_credit)
    after  = before + amount
    balance.frozen_credit = Decimal(str(after))
    tx = BalanceTransaction(
        agent_id=agent_id, tx_type="freeze", balance_type="credit",
        amount=Decimal(str(amount)), balance_before=Decimal(str(before)),
        balance_after=Decimal(str(after)),
        description=description or f"冻结授信 {amount} 点",
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
    """解冻代理的授信点数。"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="解冻金额必须大于 0")
    balance = await _get_or_create_balance(agent_id, db)
    if amount > float(balance.frozen_credit):
        raise HTTPException(
            status_code=400,
            detail=f"已冻结金额不足（已冻结: {balance.frozen_credit:.4f} 点，请求解冻: {amount:.4f} 点）",
        )
    before = float(balance.frozen_credit)
    after  = before - amount
    balance.frozen_credit = Decimal(str(after))
    tx = BalanceTransaction(
        agent_id=agent_id, tx_type="unfreeze", balance_type="credit",
        amount=Decimal(str(-amount)), balance_before=Decimal(str(before)),
        balance_after=Decimal(str(after)),
        description=description or f"解冻授信 {amount} 点",
        operated_by_admin_id=admin_id,
    )
    db.add(tx)
    await db.flush()
    return await get_agent_balance(agent_id, db)


async def get_balance_transactions(
    agent_id: int,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    tx_type: str | None = None,
) -> dict:
    """查询代理点数流水记录。"""
    query = select(BalanceTransaction).where(BalanceTransaction.agent_id == agent_id)
    if tx_type:
        query = query.where(BalanceTransaction.tx_type == tx_type)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(BalanceTransaction.created_at.desc())
        .offset(offset).limit(page_size)
    )
    txs = result.scalars().all()

    tx_type_labels = {
        "recharge": "充值", "credit": "授信", "consume": "消耗",
        "freeze": "冻结", "unfreeze": "解冻", "adjust": "调整",
    }
    return {
        "transactions": [
            {
                "id":               t.id,
                "tx_type":          t.tx_type,
                "tx_type_label":    tx_type_labels.get(t.tx_type, t.tx_type),
                "balance_type":     t.balance_type,
                "amount":           float(t.amount),
                "balance_before":   float(t.balance_before),
                "balance_after":    float(t.balance_after),
                "description":      t.description,
                "operated_by_admin_id": t.operated_by_admin_id,
                "related_user_id":  t.related_user_id,
                "related_project_id": t.related_project_id,
                "created_at":       t.created_at.isoformat(),
            }
            for t in txs
        ],
        "total":     total,
        "page":      page,
        "page_size": page_size,
    }


async def get_agents_with_balance_and_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> dict:
    """
    获取代理列表，同时附带余额和已授权项目信息。
    用于管理后台代理列表页面。
    """
    from app.models.main.models import Agent
    query = select(Agent)
    if status_filter:
        query = query.where(Agent.status == status_filter)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Agent.id.desc()).offset(offset).limit(page_size)
    )
    agents = result.scalars().all()

    if not agents:
        return {"agents": [], "total": total, "page": page, "page_size": page_size}

    agent_ids = [a.id for a in agents]

    # 批量查余额
    bal_result = await db.execute(
        select(AgentBalance).where(AgentBalance.agent_id.in_(agent_ids))
    )
    balance_map = {b.agent_id: b for b in bal_result.scalars().all()}

    # 批量查项目授权
    auth_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id.in_(agent_ids),
            AgentProjectAuth.status == "active",
        )
    )
    project_map: dict[int, list[dict]] = {}
    authorized_project_ids: set[tuple[int, int]] = set()  # (agent_id, project_id)
    for auth, project in auth_result.all():
        project_map.setdefault(auth.agent_id, []).append({
            "project_id":   project.id,
            "code_name":    project.code_name,
            "display_name": project.display_name,
            "project_type": project.project_type,
            "valid_until":  auth.valid_until.isoformat() if auth.valid_until else None,
            "user_count":   0,   # 将在下面填充
        })
        authorized_project_ids.add((auth.agent_id, project.id))

    # 批量查每个代理在每个项目下的用户数（agent_id + project_id 维度）
    if authorized_project_ids:
        proj_user_result = await db.execute(
            select(
                User.created_by_agent_id,
                Authorization.game_project_id,
                func.count(func.distinct(User.id)).label("cnt"),
            )
            .join(Authorization, User.id == Authorization.user_id)
            .where(
                User.created_by_agent_id.in_(agent_ids),
                User.is_deleted == False,
                Authorization.status == "active",
            )
            .group_by(User.created_by_agent_id, Authorization.game_project_id)
        )
        # 填充 user_count
        proj_user_map: dict[tuple[int, int], int] = {
            (row.created_by_agent_id, row.game_project_id): row.cnt
            for row in proj_user_result.all()
        }
        for agent_id_key, proj_list in project_map.items():
            for p in proj_list:
                p["user_count"] = proj_user_map.get((agent_id_key, p["project_id"]), 0)

    # 批量查用户数
    user_count_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id).label("cnt"))
        .where(User.created_by_agent_id.in_(agent_ids), User.is_deleted == False)
        .group_by(User.created_by_agent_id)
    )
    user_count_map = {row[0]: row[1] for row in user_count_result.all()}

    def _fmt_balance(b: AgentBalance | None) -> dict:
        if not b:
            return {
                "charged_points": 0.0, "credit_points": 0.0,
                "frozen_credit": 0.0, "available_total": 0.0,
            }
        return {
            "charged_points":  float(b.charged_points),
            "credit_points":   float(b.credit_points),
            "frozen_credit":   float(b.frozen_credit),
            "available_total": float(b.charged_points) + float(b.credit_points) - float(b.frozen_credit),
        }

    return {
        "agents": [
            {
                "id":              a.id,
                "username":        a.username,
                "level":           a.level,
                "status":          a.status,
                "max_users":       a.max_users,
                "users_count":     user_count_map.get(a.id, 0),
                "commission_rate": float(a.commission_rate) if a.commission_rate else None,
                "created_at":      a.created_at.isoformat(),
                "authorized_projects": project_map.get(a.id, []),
                "balance":         _fmt_balance(balance_map.get(a.id)),
            }
            for a in agents
        ],
        "total":     total,
        "page":      page,
        "page_size": page_size,
    }
