r"""
文件位置: app/routers/agents.py
文件名称: agents.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-08
版本: V1.6.3
功能说明:
    代理管理路由。

当前业务口径:
    - hierarchy_depth 表示代理组织层级 / 代理树深度。
    - tier_level 表示代理业务等级 Lv.1 - Lv.4。
    - 不兼容旧字段 level / hierarchy_level。
    - 项目编码对外统一使用 game_project_code。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - Agent 登录成功 / 失败写入 audit_log，不记录密码或 Token。
    - Agent Token 可访问 /scope/* 范围接口，只能查看/操作自己代理子树范围内的代理。
    - /scope/list 为代理端超级列表专用响应，额外补 business_profile、balance、authorized_projects[].user_count。
    - /scope 支持代理创建直属下级代理。
    - 开发期支持管理员硬删除代理，但必须先通过外键与账务事实阻断检查。

路由注册顺序:
    静态路径和 /scope/* 必须在 /{agent_id} 之前注册。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_agent
from app.core.redis_client import get_redis
from app.core.security import hash_password
from app.core.utils import get_agent_scope_ids
from app.database import get_main_db
from app.models.main.accounting import (
    AccountingAdjustmentRequest,
    AccountingDocument,
    AccountingLedgerEntry,
    AccountingReconciliationItem,
    AccountingWallet,
    AgentMonthlyBill,
    AuthorizationChargeSnapshot,
)
from app.models.main.agent_profile import AgentBusinessProfile
from app.models.main.models import (
    Admin,
    Agent,
    AgentProjectAuth,
    Authorization,
    GameProject,
    User,
)
from app.models.main.project_access import AgentLevelPolicy
from app.schemas.agent import (
    AgentCreateRequest,
    AgentFlatListResponse,
    AgentListResponse,
    AgentLoginRequest,
    AgentLoginResponse,
    AgentResponse,
    AgentSubtreeResponse,
    AgentUpdateRequest,
)
from app.schemas.agent_me import AgentMeResponse
from app.services.accounting_service import get_agent_balance, get_balance_transactions
from app.services.agent_service import (
    agent_login,
    create_agent,
    get_agent,
    get_agent_subtree,
    list_agents,
    list_agents_in_scope,
    update_agent,
)
from app.services.audit_service import create_audit_log

router = APIRouter()


def _as_float(value) -> float:
    return float(value or 0)


def _money_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _count_rows(db: AsyncSession, model, *where_clauses) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(*where_clauses)
    )
    return int(result.scalar_one() or 0)


async def _business_profile_dict(
    *,
    db: AsyncSession,
    agent_id: int,
) -> dict:
    """
    获取代理业务画像摘要。

    注意:
      - 本函数用于代理端 scope/list 超级列表展示。
      - 不创建缺失画像，避免列表查询产生写入副作用。
      - 缺失画像时返回 Lv.1 默认展示值。
    """
    profile_result = await db.execute(
        select(AgentBusinessProfile).where(AgentBusinessProfile.agent_id == agent_id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        return {
            "agent_id": agent_id,
            "tier_level": 1,
            "tier_name": "Lv.1 新手代理",
            "risk_status": "normal",
            "remark": None,
            "credit_limit": 0.0,
            "max_credit_limit": 0.0,
            "credit_limit_override": None,
            "max_credit_limit_override": None,
            "can_create_sub_agents": False,
            "max_sub_agents": 0,
            "can_create_sub_agents_override": None,
            "max_sub_agents_override": None,
        }

    policy_result = await db.execute(
        select(AgentLevelPolicy).where(AgentLevelPolicy.level == profile.tier_level)
    )
    policy = policy_result.scalar_one_or_none()

    tier_name = policy.level_name if policy else f"Lv.{profile.tier_level}"

    credit_limit = (
        _as_float(profile.credit_limit_override)
        if profile.credit_limit_override is not None
        else _as_float(policy.default_credit_limit if policy else 0)
    )

    max_credit_limit = (
        _as_float(profile.max_credit_limit_override)
        if profile.max_credit_limit_override is not None
        else _as_float(policy.max_credit_limit if policy else 0)
    )

    can_create_sub_agents = (
        bool(profile.can_create_sub_agents_override)
        if profile.can_create_sub_agents_override is not None
        else bool(policy.can_create_sub_agents if policy else False)
    )

    max_sub_agents = (
        int(profile.max_sub_agents_override)
        if profile.max_sub_agents_override is not None
        else int(policy.max_sub_agents if policy else 0)
    )

    return {
        "agent_id": agent_id,
        "tier_level": profile.tier_level,
        "tier_name": tier_name,
        "risk_status": profile.risk_status,
        "remark": profile.remark,
        "credit_limit": credit_limit,
        "max_credit_limit": max_credit_limit,
        "credit_limit_override": (
            _as_float(profile.credit_limit_override)
            if profile.credit_limit_override is not None
            else None
        ),
        "max_credit_limit_override": (
            _as_float(profile.max_credit_limit_override)
            if profile.max_credit_limit_override is not None
            else None
        ),
        "can_create_sub_agents": can_create_sub_agents,
        "max_sub_agents": max_sub_agents,
        "can_create_sub_agents_override": profile.can_create_sub_agents_override,
        "max_sub_agents_override": profile.max_sub_agents_override,
    }


async def _balance_dict(
    *,
    db: AsyncSession,
    agent_id: int,
) -> dict:
    """
    获取代理钱包余额摘要。

    注意:
      - 本函数用于列表展示。
      - 不自动创建钱包，避免列表查询产生写入副作用。
      - 无钱包时返回 0 余额。
    """
    result = await db.execute(
        select(AccountingWallet).where(AccountingWallet.agent_id == agent_id)
    )
    wallet = result.scalar_one_or_none()

    if wallet is None:
        return {
            "agent_id": agent_id,
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
            "status": "active",
            "risk_status": "normal",
        }

    charged = _money_float(wallet.charged_balance)
    credit = _money_float(wallet.credit_balance)
    frozen = _money_float(wallet.frozen_credit)
    available_credit = credit - frozen
    available_total = charged + available_credit

    return {
        "agent_id": agent_id,
        "charged_balance": charged,
        "credit_balance": credit,
        "frozen_credit": frozen,
        "available_credit": available_credit,
        "available_total": available_total,
        "total_recharged": _money_float(wallet.total_recharged),
        "total_credited": _money_float(wallet.total_credited),
        "total_consumed": _money_float(wallet.total_consumed),
        "total_refunded": _money_float(wallet.total_refunded),
        "total_adjusted": _money_float(wallet.total_adjusted),
        "status": wallet.status,
        "risk_status": wallet.risk_status,
    }


async def _fill_scope_authorized_project_user_counts(
    *,
    db: AsyncSession,
    data: dict,
) -> dict:
    """
    回填代理端 scope/list 的 authorized_projects[].user_count。

    统计口径:
      - User.created_by_agent_id = 代理 ID
      - User.is_deleted = False
      - Authorization.status = active
      - Authorization.game_project_id = 项目 ID
    """
    agents = data.get("agents") or []
    agent_ids = [
        int(item["id"])
        for item in agents
        if item.get("id") is not None
    ]

    if not agent_ids:
        return data

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

    count_map = {
        (int(agent_id), int(project_id)): int(count)
        for agent_id, project_id, count in count_result.all()
        if agent_id is not None and project_id is not None
    }

    for item in agents:
        agent_id = item.get("id")
        if agent_id is None:
            continue

        projects = item.get("authorized_projects") or []
        item["authorized_projects"] = projects

        for project in projects:
            project_id = (
                project.get("project_id")
                or project.get("id")
                or project.get("game_project_id")
            )

            if project_id is None:
                project["user_count"] = 0
                continue

            project["user_count"] = count_map.get(
                (int(agent_id), int(project_id)),
                0,
            )

    return data


async def _enrich_scope_agent_list(
    *,
    db: AsyncSession,
    result: AgentFlatListResponse,
) -> dict:
    """
    为代理端超级列表补齐业务画像、余额、授权项目直属用户数。

    返回 dict 而不是 AgentFlatListResponse:
      - 避免 Pydantic response_model 过滤 business_profile / balance。
      - 仅作用于 /scope/list，不影响管理员普通代理列表接口。
    """
    data = result.model_dump(mode="json")

    for item in data.get("agents", []):
        agent_id = int(item["id"])
        item["business_profile"] = await _business_profile_dict(
            db=db,
            agent_id=agent_id,
        )
        item["balance"] = await _balance_dict(
            db=db,
            agent_id=agent_id,
        )

    data = await _fill_scope_authorized_project_user_counts(
        db=db,
        data=data,
    )

    return data


async def _assert_agent_in_scope(
    *,
    db: AsyncSession,
    current_agent: Agent,
    target_agent_id: int,
    allow_self: bool = True,
) -> None:
    """校验 target_agent_id 是否在当前代理权限子树内。"""
    if not allow_self and target_agent_id == current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理不能在此入口操作自己的代理账号",
        )

    scope_ids = await get_agent_scope_ids(db, current_agent.id)
    if target_agent_id not in scope_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该代理",
        )


async def _get_agent_delete_blockers(
    *,
    db: AsyncSession,
    agent_id: int,
) -> dict[str, int]:
    """
    获取代理硬删除阻断项。

    硬删除边界:
      - 有下级代理时不能删除，否则会破坏代理树。
      - 有直属用户时不能删除，否则会破坏用户创建关系。
      - 有不可变账务事实时不能删除，否则会破坏账务审计。
      - 纯配置类关系如项目授权、业务画像、空钱包允许在删除前清理。
    """
    blockers = {
        "child_agents": await _count_rows(
            db,
            Agent,
            Agent.parent_agent_id == agent_id,
        ),
        "direct_users": await _count_rows(
            db,
            User,
            User.created_by_agent_id == agent_id,
        ),
        "accounting_documents": await _count_rows(
            db,
            AccountingDocument,
            AccountingDocument.agent_id == agent_id,
        ),
        "ledger_entries": await _count_rows(
            db,
            AccountingLedgerEntry,
            AccountingLedgerEntry.agent_id == agent_id,
        ),
        "authorization_charge_snapshots": await _count_rows(
            db,
            AuthorizationChargeSnapshot,
            AuthorizationChargeSnapshot.agent_id == agent_id,
        ),
        "reconciliation_items": await _count_rows(
            db,
            AccountingReconciliationItem,
            AccountingReconciliationItem.agent_id == agent_id,
        ),
        "adjustment_requests": await _count_rows(
            db,
            AccountingAdjustmentRequest,
            AccountingAdjustmentRequest.agent_id == agent_id,
        ),
        "monthly_bills": await _count_rows(
            db,
            AgentMonthlyBill,
            AgentMonthlyBill.agent_id == agent_id,
        ),
    }

    return {key: value for key, value in blockers.items() if value > 0}


async def _cleanup_agent_config_rows(
    *,
    db: AsyncSession,
    agent_id: int,
) -> None:
    """
    硬删除代理前清理配置类关联记录。

    只清理可重建、非账务事实类记录:
      - AgentProjectAuth
      - AgentBusinessProfile
      - AccountingWallet 空钱包快照

    不清理:
      - AccountingDocument
      - AccountingLedgerEntry
      - AuthorizationChargeSnapshot
      - 对账 / 调账 / 月账单
    这些在 _get_agent_delete_blockers 中已作为阻断项。
    """
    await db.execute(
        delete(AgentProjectAuth).where(AgentProjectAuth.agent_id == agent_id)
    )
    await db.execute(
        delete(AgentBusinessProfile).where(AgentBusinessProfile.agent_id == agent_id)
    )
    await db.execute(
        delete(AccountingWallet).where(AccountingWallet.agent_id == agent_id)
    )


# ── 登录 ──────────────────────────────────────────────────────

@router.post("/auth/login", response_model=AgentLoginResponse)
async def agent_login_endpoint(
    body: AgentLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_main_db),
) -> AgentLoginResponse:
    """代理登录，返回 Agent Token。"""
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    try:
        result = await agent_login(body=body, db=db)
    except HTTPException as exc:
        await create_audit_log(
            db=db,
            actor_type="agent",
            actor_id=None,
            action="auth.agent.login_failed",
            target_type="agent",
            target_id=body.username,
            summary=f"代理 {body.username} 登录失败",
            metadata={
                "username": body.username,
                "success": False,
                "status_code": exc.status_code,
                "reason": str(exc.detail),
            },
            ip_address=ip,
            user_agent=user_agent,
        )
        await db.commit()
        raise

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=result.agent_id,
        action="auth.agent.login_success",
        target_type="agent",
        target_id=result.agent_id,
        summary=f"代理 {result.username} 登录成功",
        metadata={
            "agent_id": result.agent_id,
            "username": result.username,
            "hierarchy_depth": result.hierarchy_depth,
            "success": True,
            "expires_in": result.expires_in,
        },
        ip_address=ip,
        user_agent=user_agent,
    )

    return result


# ── 代理个人主页（静态路径，必须在 /{agent_id} 之前）──────────

@router.get("/me", response_model=AgentMeResponse, summary="代理个人主页")
async def get_my_profile(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentMeResponse:
    """代理获取自己的详细个人信息（Agent Token）。"""
    users_total = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == current_agent.id
            )
        )
    ).scalar_one()

    users_active = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == current_agent.id,
                User.status == "active",
            )
        )
    ).scalar_one()

    users_suspended = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == current_agent.id,
                User.status == "suspended",
            )
        )
    ).scalar_one()

    profile = await _business_profile_dict(
        db=db,
        agent_id=current_agent.id,
    )

    proj_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id == current_agent.id,
            AgentProjectAuth.status == "active",
            GameProject.is_active == True,  # noqa: E712
        )
        .order_by(GameProject.display_name)
    )

    now = datetime.now(tz=timezone.utc)
    authorized_projects: list[dict] = []

    for auth, project in proj_result.all():
        valid_until = _aware(auth.valid_until)
        authorized_projects.append(
            {
                "id": project.id,
                "display_name": project.display_name,
                "game_project_code": project.code_name,
                "project_type": project.project_type,
                "valid_until": valid_until,
                "is_expired": valid_until is not None and valid_until <= now,
            }
        )

    parent_info = None
    if current_agent.parent_agent_id:
        parent = await db.get(Agent, current_agent.parent_agent_id)
        if parent:
            parent_info = {
                "id": parent.id,
                "username": parent.username,
                "hierarchy_depth": parent.hierarchy_depth,
            }

    return AgentMeResponse(
        id=current_agent.id,
        username=current_agent.username,
        hierarchy_depth=current_agent.hierarchy_depth,
        status=current_agent.status,
        created_at=current_agent.created_at,
        updated_at=current_agent.updated_at,
        commission_rate=(
            float(current_agent.commission_rate)
            if current_agent.commission_rate is not None
            else None
        ),
        parent_agent=parent_info,
        users_total=users_total,
        users_active=users_active,
        users_suspended=users_suspended,
        authorized_projects=authorized_projects,
        tier_level=profile["tier_level"],
        tier_name=profile["tier_name"],
        risk_status=profile["risk_status"],
        remark=profile.get("remark"),
        credit_limit=profile["credit_limit"],
        max_credit_limit=profile["max_credit_limit"],
        credit_limit_override=profile.get("credit_limit_override"),
        max_credit_limit_override=profile.get("max_credit_limit_override"),
        can_create_sub_agents=profile["can_create_sub_agents"],
        max_sub_agents=profile["max_sub_agents"],
        can_create_sub_agents_override=profile.get("can_create_sub_agents_override"),
        max_sub_agents_override=profile.get("max_sub_agents_override"),
        can_auto_open_project=False,
        auto_open_project_limit=0,
        review_priority=0,
    )


@router.get("/me/dashboard", summary="代理端总览（单次请求）")
async def agent_dashboard(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
    redis = Depends(get_redis),
) -> dict:
    """代理端仪表盘 — 身份卡 + 指标 + 项目 + 到期预警 + 下级代理。"""
    now = datetime.now(tz=timezone.utc)

    # ── 身份卡（Lv.2+ 显示） ──────────────────────────────
    profile = await _business_profile_dict(db=db, agent_id=current_agent.id)
    wallet = await _balance_dict(db=db, agent_id=current_agent.id)

    # ── 直属用户统计 ──────────────────────────────────────
    users_total = (await db.execute(
        select(func.count(User.id)).where(User.created_by_agent_id == current_agent.id)
    )).scalar_one()
    users_active = (await db.execute(
        select(func.count(User.id)).where(
            User.created_by_agent_id == current_agent.id, User.status == "active"
        )
    )).scalar_one()

    # ── 授权项目一览 ──────────────────────────────────────
    proj_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id == current_agent.id, AgentProjectAuth.status == "active")
        .order_by(GameProject.display_name)
    )
    projects = []
    for _auth, proj in proj_result.all():
        user_count = (await db.execute(
            select(func.count(Authorization.id)).where(
                Authorization.game_project_id == proj.id,
                Authorization.status == "active",
                Authorization.user_id.in_(
                    select(User.id).where(User.created_by_agent_id == current_agent.id)
                ),
            )
        )).scalar_one()
        projects.append({
            "code": proj.code_name, "display": proj.display_name,
            "user_count": user_count, "online": 0,
        })

    # ── 在线设备数 ────────────────────────────────────────
    try:
        from app.core.redis_client import get_all_heartbeats_for_game
        online_count = 0
        for p in projects:
            hbs = await get_all_heartbeats_for_game(redis, (await db.execute(
                select(GameProject.id).where(GameProject.code_name == p["code"])
            )).scalar_one())
            online = sum(1 for h in hbs if h["user_id"] in (
                await db.execute(select(User.id).where(User.created_by_agent_id == current_agent.id))
            ).scalars().all())
            p["online"] = online
            online_count += online
    except Exception:
        online_count = 0

    # ── 即将到期授权 ──────────────────────────────────────
    week_later = now + timedelta(days=7)
    expiring_result = await db.execute(
        select(Authorization, User, GameProject)
        .join(User, Authorization.user_id == User.id)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(
            Authorization.status == "active",
            Authorization.valid_until.is_not(None),
            Authorization.valid_until > now,
            Authorization.valid_until <= week_later,
            User.created_by_agent_id == current_agent.id,
        )
        .order_by(Authorization.valid_until.asc()).limit(5)
    )
    expiring = [
        {"user": u.username, "level": a.user_level, "project": p.display_name,
         "days": max(1, (a.valid_until - now).days + 1)}
        for a, u, p in expiring_result.all()
    ]

    # ── 下级代理 ──────────────────────────────────────────
    sub_agents = {"can_create": profile.get("can_create_sub_agents", False), "list": []}
    if profile.get("can_create_sub_agents"):
        scope_ids = await get_agent_scope_ids(db, current_agent.id)
        scope_ids = [i for i in scope_ids if i != current_agent.id]
        if scope_ids:
            sub_result = await db.execute(
                select(Agent).where(Agent.id.in_(scope_ids)).order_by(Agent.hierarchy_depth, Agent.id)
            )
            for sub in sub_result.scalars().all():
                sub_wallet = await _balance_dict(db=db, agent_id=sub.id)
                sub_users = (await db.execute(
                    select(func.count(User.id)).where(User.created_by_agent_id == sub.id)
                )).scalar_one()
                sub_profile = await _business_profile_dict(db=db, agent_id=sub.id)
                sub_agents["list"].append({
                    "id": sub.id, "username": sub.username,
                    "hierarchy_depth": sub.hierarchy_depth,
                    "tier_level": sub_profile.get("tier_level", 1),
                    "tier_name": sub_profile.get("tier_name", "Lv.1"),
                    "users": sub_users, "balance": sub_wallet.get("available_total", 0),
                    "is_direct": sub.parent_agent_id == current_agent.id,
                })

    # ── 下级代理到期预警 ────────────────────────────────
    sub_expiring = []
    if profile.get("can_create_sub_agents"):
        sub_scope_ids = await get_agent_scope_ids(db, current_agent.id)
        sub_scope_ids = [i for i in sub_scope_ids if i != current_agent.id]
        if sub_scope_ids:
            sub_exp_result = await db.execute(
                select(Authorization, User, GameProject, Agent)
                .join(User, Authorization.user_id == User.id)
                .join(GameProject, Authorization.game_project_id == GameProject.id)
                .join(Agent, User.created_by_agent_id == Agent.id)
                .where(
                    Authorization.status == "active",
                    Authorization.valid_until.is_not(None),
                    Authorization.valid_until > now,
                    Authorization.valid_until <= week_later,
                    User.created_by_agent_id.in_(sub_scope_ids),
                )
                .order_by(Authorization.valid_until.asc()).limit(5)
            )
            sub_expiring = [
                {"user": u.username, "level": a.user_level, "project": p.display_name,
                 "agent": ag.username, "days": max(1, (a.valid_until - now).days + 1)}
                for a, u, p, ag in sub_exp_result.all()
            ]

    return {
        "agent": {
            "username": current_agent.username,
            "hierarchy_depth": current_agent.hierarchy_depth,
            "tier_level": profile.get("tier_level", 1),
            "tier_name": profile.get("tier_name", ""),
            "risk_status": profile.get("risk_status", "normal"),
        },
        "wallet": wallet,
        "users": {"total": users_total, "active": users_active},
        "online_devices": online_count,
        "projects": projects,
        "expiring_auths": expiring,
        "sub_agents": sub_agents,
        "sub_expiring_auths": sub_expiring,
    }


# ── 代理自查余额与流水 ───────────────────────────────────────

@router.get("/my/balance", summary="代理查询自己余额")
async def my_balance(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_agent_balance(current_agent.id, db)


@router.get("/my/transactions", summary="代理查询自己流水")
async def my_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    entry_type: str | None = Query(default=None),
    related_user_id: int | None = Query(default=None),
    related_project_id: int | None = Query(default=None),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(
        agent_id=current_agent.id,
        db=db,
        page=page,
        page_size=page_size,
        entry_type=entry_type,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
    )


# ── 已授权项目列表（静态路径）────────────────────────────────

@router.get("/my-projects", response_model=list[dict])
async def get_my_authorized_projects(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    """代理获取自己已授权的项目列表（Agent Token）。"""
    result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id == current_agent.id,
            AgentProjectAuth.status == "active",
            GameProject.is_active == True,  # noqa: E712
        )
        .order_by(GameProject.display_name)
    )

    now = datetime.now(tz=timezone.utc)
    projects: list[dict] = []

    for auth, project in result.all():
        valid_until = _aware(auth.valid_until)
        if valid_until is not None and valid_until <= now:
            continue

        projects.append(
            {
                "id": project.id,
                "display_name": project.display_name,
                "game_project_code": project.code_name,
                "project_type": project.project_type,
                "auth_valid_until": valid_until,
            }
        )

    return projects


# ── 权限范围：创建直属下级代理 ───────────────────────────────

@router.post("/scope", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_in_scope_endpoint(
    body: AgentCreateRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    """
    代理创建直属下级代理。

    规则:
      - 当前登录代理作为 parent_agent_id。
      - 不允许代理端指定任意 parent_agent_id。
      - 新下级 hierarchy_depth = 当前代理 hierarchy_depth + 1。
      - 业务画像默认由后续策略治理，不在此接口由代理端设置。
    """
    # ── 前置校验：用户名唯一性 ──
    exists_result = await db.execute(
        select(Agent).where(Agent.username == body.username)
    )
    if exists_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"代理用户名 '{body.username}' 已存在",
        )

    # ── 前置校验：业务画像与权限 ──
    current_profile = await _business_profile_dict(
        db=db,
        agent_id=current_agent.id,
    )

    if not current_profile.get("can_create_sub_agents", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前代理业务画像不允许创建下级代理",
        )

    # ── 前置校验：创建前计数（不含本次请求）──
    max_sub = int(current_profile.get("max_sub_agents", 0) or 0)
    if max_sub > 0:
        existing_subs = await _count_rows(
            db, Agent, Agent.parent_agent_id == current_agent.id
        )
        if existing_subs >= max_sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"当前代理下级代理数已达上限（{max_sub} 个）",
            )

    # ── 前置校验：业务等级 ──
    parent_tier_level = int(current_profile["tier_level"] or 0)
    child_tier_level = parent_tier_level - 1

    if child_tier_level < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前代理业务等级不允许创建下级代理",
        )

    # ── 所有前置校验通过，创建 Agent ──
    child = Agent(
        username=body.username,
        password_hash=hash_password(body.password),
        parent_agent_id=current_agent.id,
        hierarchy_depth=int(current_agent.hierarchy_depth) + 1,
        created_by_admin_id=None,
        commission_rate=body.commission_rate,
        status="active",
    )

    db.add(child)
    await db.flush()
    await db.refresh(child)

    child_profile = AgentBusinessProfile(
        agent_id=child.id,
        tier_level=child_tier_level,
        risk_status="normal",
    )
    db.add(child_profile)
    await db.flush()

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.create",
        target_type="agent",
        target_id=child.id,
        summary=f"代理 {current_agent.username} 创建下级代理 {child.username}",
        metadata={
            "operator_agent_id": current_agent.id,
            "child_agent_id": child.id,
            "child_username": child.username,
            "parent_agent_id": child.parent_agent_id,
            "hierarchy_depth": child.hierarchy_depth,
            "commission_rate": (
                float(child.commission_rate)
                if child.commission_rate is not None
                else None
            ),
        },
    )

    return await get_agent(agent_id=child.id, db=db)


# ── 权限范围列表（静态路径）──────────────────────────────────

@router.get("/scope/list")
async def list_agents_in_scope_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """
    代理查看自己权限范围内的所有代理（Agent Token）。

    返回字段比 AgentFlatListResponse 更多:
      - business_profile
      - balance
      - authorized_projects[].user_count
    """
    result = await list_agents_in_scope(
        scope_agent_id=current_agent.id,
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return await _enrich_scope_agent_list(
        db=db,
        result=result,
    )


@router.get("/scope/{agent_id}", response_model=AgentResponse)
async def get_agent_in_scope_endpoint(
    agent_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    """代理查看自己权限范围内的代理详情。"""
    await _assert_agent_in_scope(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await get_agent(agent_id=agent_id, db=db)


@router.get("/scope/{agent_id}/subtree", response_model=AgentSubtreeResponse)
async def get_agent_subtree_in_scope_endpoint(
    agent_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentSubtreeResponse:
    """代理查看自己权限范围内某个代理的子树。"""
    await _assert_agent_in_scope(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await get_agent_subtree(root_agent_id=agent_id, db=db)


@router.patch("/scope/{agent_id}", response_model=AgentResponse)
async def update_agent_in_scope_endpoint(
    agent_id: int,
    body: AgentUpdateRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    """
    代理更新自己权限范围内的下级代理基础信息。

    注意:
      - 代理不能在此入口操作自己的代理账号。
    """
    await _assert_agent_in_scope(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
        allow_self=False,
    )

    result = await update_agent(
        agent_id=agent_id,
        body=body,
        db=db,
    )

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.update",
        target_type="agent",
        target_id=result.id,
        summary=f"代理 {current_agent.username} 更新下级代理 {result.username}",
        metadata={
            "operator_agent_id": current_agent.id,
            "target_agent_id": result.id,
            "changed_fields": body.model_dump(exclude_unset=True),
            "status": result.status,
            "commission_rate": result.commission_rate,
        },
    )

    return result


# ── 创建 / 列表（Admin）──────────────────────────────────────

@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(
    body: AgentCreateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    result = await create_agent(body=body, admin=current_admin, db=db)

    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent.create",
        target_type="agent",
        target_id=result.id,
        summary=f"创建代理 {result.username}",
        metadata={
            "agent_id": result.id,
            "username": result.username,
            "parent_agent_id": result.parent_agent_id,
            "hierarchy_depth": result.hierarchy_depth,
            "commission_rate": result.commission_rate,
            "status": result.status,
            "created_by_admin_id": result.created_by_admin_id,
        },
    )

    return result


@router.get("/", response_model=AgentListResponse)
async def list_agents_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentListResponse:
    return await list_agents(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )


# ── 全代理树（Admin，静态路径）───────────────────────────────

@router.get("/tree", response_model=list[AgentSubtreeResponse])
async def get_full_agent_tree(
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> list[AgentSubtreeResponse]:
    result = await db.execute(
        select(Agent).where(Agent.parent_agent_id.is_(None)).order_by(Agent.id)
    )
    top_agents = result.scalars().all()

    trees = []
    for agent in top_agents:
        subtree = await get_agent_subtree(agent.id, db)
        trees.append(subtree)

    return trees


# ── 参数化路径（必须在所有静态路径之后）─────────────────────

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_endpoint(
    agent_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    return await get_agent(agent_id=agent_id, db=db)


@router.get("/{agent_id}/subtree", response_model=AgentSubtreeResponse)
async def get_agent_subtree_endpoint(
    agent_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentSubtreeResponse:
    return await get_agent_subtree(root_agent_id=agent_id, db=db)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent_endpoint(
    agent_id: int,
    body: AgentUpdateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    result = await update_agent(
        agent_id=agent_id,
        body=body,
        db=db,
    )

    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent.update",
        target_type="agent",
        target_id=result.id,
        summary=f"更新代理 {result.username}",
        metadata={
            "agent_id": result.id,
            "username": result.username,
            "changed_fields": body.model_dump(exclude_unset=True),
            "status": result.status,
            "commission_rate": result.commission_rate,
        },
    )

    return result


@router.delete("/{agent_id}", summary="管理员硬删除代理")
async def delete_agent_endpoint(
    agent_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """
    管理员硬删除代理。

    说明:
      - 仅开发/测试环境可用。生产环境拒绝执行，防止误操作。
      - 本接口执行数据库硬删除，不做软删除。
      - 为避免破坏代理树、用户归属和账务事实，只允许删除"无业务事实"的代理。
      - 删除前会清理可重建配置类记录。
    """
    from app.config import settings

    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="生产环境不允许硬删除代理。如需删除请走软删除或迁移流程。",
        )
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在",
        )

    blockers = await _get_agent_delete_blockers(
        db=db,
        agent_id=agent_id,
    )

    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "该代理存在业务关联，不能硬删除。请先迁移或清理关联数据。",
                "blockers": blockers,
            },
        )

    metadata = {
        "agent_id": agent.id,
        "username": agent.username,
        "parent_agent_id": agent.parent_agent_id,
        "hierarchy_depth": agent.hierarchy_depth,
        "status": agent.status,
    }

    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent.hard_delete",
        target_type="agent",
        target_id=agent.id,
        summary=f"硬删除代理 {agent.username}",
        metadata=metadata,
    )

    await _cleanup_agent_config_rows(
        db=db,
        agent_id=agent_id,
    )

    await db.delete(agent)
    await db.flush()

    return {
        "deleted": True,
        "agent_id": agent_id,
        "username": metadata["username"],
    }