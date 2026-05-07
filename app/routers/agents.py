r"""
文件位置: app/routers/agents.py
文件名称: agents.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-08
版本: V1.6.2
功能说明:
    代理管理路由。

当前业务口径:
    - hierarchy_depth 表示代理组织层级 / 代理树深度。
    - tier_level 表示代理业务等级 Lv.1 - Lv.4。
    - Agent Token 可访问 /scope/* 范围接口，只能查看/操作自己代理子树范围内的代理。
    - /scope/list 为代理端超级列表专用响应，额外补 business_profile 与 balance，避免前端调用 Admin-only 接口。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_agent
from app.core.utils import get_agent_scope_ids
from app.database import get_main_db
from app.models.main.accounting import (
    AccountingAdjustmentRequest,
    AccountingDocument,
    AccountingLedgerEntry,
    AccountingReconciliationItem,
    AgentMonthlyBill,
    AuthorizationChargeSnapshot,
)
from app.models.main.agent_profile import AgentBusinessProfile
from app.models.main.models import Admin, Agent, AgentProjectAuth, GameProject, User
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


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _count_rows(db: AsyncSession, model, *where_clauses) -> int:
    result = await db.execute(select(func.count()).select_from(model).where(*where_clauses))
    return int(result.scalar_one() or 0)


async def _business_profile_dict(db: AsyncSession, agent_id: int) -> dict:
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
            "credit_limit": 0.0,
            "max_credit_limit": 0.0,
            "can_create_sub_agents": False,
            "max_sub_agents": 0,
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
        "credit_limit_override": _as_float(profile.credit_limit_override) if profile.credit_limit_override is not None else None,
        "max_credit_limit_override": _as_float(profile.max_credit_limit_override) if profile.max_credit_limit_override is not None else None,
        "can_create_sub_agents": can_create_sub_agents,
        "max_sub_agents": max_sub_agents,
        "can_create_sub_agents_override": profile.can_create_sub_agents_override,
        "max_sub_agents_override": profile.max_sub_agents_override,
    }


async def _enrich_scope_agent_list(
    *,
    db: AsyncSession,
    result: AgentFlatListResponse,
) -> dict:
    data = result.model_dump(mode="json")
    for item in data.get("agents", []):
        agent_id = int(item["id"])
        item["business_profile"] = await _business_profile_dict(db, agent_id)
        item["balance"] = await get_agent_balance(agent_id, db)
    return data


async def _assert_agent_in_scope(
    *,
    db: AsyncSession,
    current_agent: Agent,
    target_agent_id: int,
    allow_self: bool = True,
) -> None:
    if not allow_self and target_agent_id == current_agent.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="代理不能在此入口操作自己的代理账号")
    scope_ids = await get_agent_scope_ids(db, current_agent.id)
    if target_agent_id not in scope_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该代理")


async def _get_agent_delete_blockers(*, db: AsyncSession, agent_id: int) -> dict[str, int]:
    blockers = {
        "child_agents": await _count_rows(db, Agent, Agent.parent_agent_id == agent_id),
        "direct_users": await _count_rows(db, User, User.created_by_agent_id == agent_id),
        "accounting_documents": await _count_rows(db, AccountingDocument, AccountingDocument.agent_id == agent_id),
        "ledger_entries": await _count_rows(db, AccountingLedgerEntry, AccountingLedgerEntry.agent_id == agent_id),
        "authorization_charge_snapshots": await _count_rows(db, AuthorizationChargeSnapshot, AuthorizationChargeSnapshot.agent_id == agent_id),
        "reconciliation_items": await _count_rows(db, AccountingReconciliationItem, AccountingReconciliationItem.agent_id == agent_id),
        "adjustment_requests": await _count_rows(db, AccountingAdjustmentRequest, AccountingAdjustmentRequest.agent_id == agent_id),
        "monthly_bills": await _count_rows(db, AgentMonthlyBill, AgentMonthlyBill.agent_id == agent_id),
    }
    return {key: value for key, value in blockers.items() if value > 0}


@router.post("/auth/login", response_model=AgentLoginResponse)
async def agent_login_endpoint(body: AgentLoginRequest, request: Request, db: AsyncSession = Depends(get_main_db)) -> AgentLoginResponse:
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
            metadata={"username": body.username, "success": False, "status_code": exc.status_code, "reason": str(exc.detail)},
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
        metadata={"agent_id": result.agent_id, "username": result.username, "hierarchy_depth": result.hierarchy_depth, "success": True, "expires_in": result.expires_in},
        ip_address=ip,
        user_agent=user_agent,
    )
    return result


@router.get("/me", response_model=AgentMeResponse, summary="代理个人主页")
async def get_my_profile(current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> AgentMeResponse:
    users_total = (await db.execute(select(func.count(User.id)).where(User.created_by_agent_id == current_agent.id))).scalar_one()
    users_active = (await db.execute(select(func.count(User.id)).where(User.created_by_agent_id == current_agent.id, User.status == "active"))).scalar_one()
    users_suspended = (await db.execute(select(func.count(User.id)).where(User.created_by_agent_id == current_agent.id, User.status == "suspended"))).scalar_one()

    profile = await _business_profile_dict(db, current_agent.id)

    proj_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id == current_agent.id, AgentProjectAuth.status == "active", GameProject.is_active == True)  # noqa: E712
        .order_by(GameProject.display_name)
    )
    now = datetime.now(tz=timezone.utc)
    authorized_projects: list[dict] = []
    for auth, project in proj_result.all():
        valid_until = _aware(auth.valid_until)
        authorized_projects.append({
            "id": project.id,
            "display_name": project.display_name,
            "game_project_code": project.code_name,
            "project_type": project.project_type,
            "valid_until": valid_until,
            "is_expired": valid_until is not None and valid_until <= now,
        })

    parent_info = None
    if current_agent.parent_agent_id:
        parent = await db.get(Agent, current_agent.parent_agent_id)
        if parent:
            parent_info = {"id": parent.id, "username": parent.username, "hierarchy_depth": parent.hierarchy_depth}

    return AgentMeResponse(
        id=current_agent.id,
        username=current_agent.username,
        hierarchy_depth=current_agent.hierarchy_depth,
        status=current_agent.status,
        created_at=current_agent.created_at,
        updated_at=current_agent.updated_at,
        commission_rate=float(current_agent.commission_rate) if current_agent.commission_rate is not None else None,
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


@router.get("/my/balance", summary="代理查询自己余额")
async def my_balance(current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> dict:
    return await get_agent_balance(current_agent.id, db)


@router.get("/my/transactions", summary="代理查询自己流水")
async def my_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tx_type: str | None = Query(default=None),
    related_user_id: int | None = Query(default=None),
    related_project_id: int | None = Query(default=None),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(agent_id=current_agent.id, db=db, page=page, page_size=page_size, tx_type=tx_type, related_user_id=related_user_id, related_project_id=related_project_id)


@router.get("/my-projects", response_model=list[dict])
async def get_my_authorized_projects(current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> list[dict]:
    result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id == current_agent.id, AgentProjectAuth.status == "active", GameProject.is_active == True)  # noqa: E712
        .order_by(GameProject.display_name)
    )
    now = datetime.now(tz=timezone.utc)
    projects: list[dict] = []
    for auth, project in result.all():
        valid_until = _aware(auth.valid_until)
        if valid_until is not None and valid_until <= now:
            continue
        projects.append({"id": project.id, "display_name": project.display_name, "game_project_code": project.code_name, "project_type": project.project_type, "auth_valid_until": valid_until})
    return projects


@router.get("/scope/list")
async def list_agents_in_scope_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    result = await list_agents_in_scope(scope_agent_id=current_agent.id, db=db, page=page, page_size=page_size, status_filter=status_filter)
    return await _enrich_scope_agent_list(db=db, result=result)


@router.get("/scope/{agent_id}", response_model=AgentResponse)
async def get_agent_in_scope_endpoint(agent_id: int, current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> AgentResponse:
    await _assert_agent_in_scope(db=db, current_agent=current_agent, target_agent_id=agent_id)
    return await get_agent(agent_id=agent_id, db=db)


@router.get("/scope/{agent_id}/subtree", response_model=AgentSubtreeResponse)
async def get_agent_subtree_in_scope_endpoint(agent_id: int, current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> AgentSubtreeResponse:
    await _assert_agent_in_scope(db=db, current_agent=current_agent, target_agent_id=agent_id)
    return await get_agent_subtree(root_agent_id=agent_id, db=db)


@router.patch("/scope/{agent_id}", response_model=AgentResponse)
async def update_agent_in_scope_endpoint(agent_id: int, body: AgentUpdateRequest, current_agent: Agent = Depends(get_current_agent), db: AsyncSession = Depends(get_main_db)) -> AgentResponse:
    await _assert_agent_in_scope(db=db, current_agent=current_agent, target_agent_id=agent_id, allow_self=False)
    result = await update_agent(agent_id=agent_id, body=body, db=db)
    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.update",
        target_type="agent",
        target_id=result.id,
        summary=f"代理 {current_agent.username} 更新下级代理 {result.username}",
        metadata={"operator_agent_id": current_agent.id, "target_agent_id": result.id, "changed_fields": body.model_dump(exclude_unset=True), "status": result.status, "commission_rate": result.commission_rate},
    )
    return result


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(body: AgentCreateRequest, current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> AgentResponse:
    result = await create_agent(body=body, admin=current_admin, db=db)
    await create_audit_log(db=db, actor_type="admin", actor_id=current_admin.id, action="agent.create", target_type="agent", target_id=result.id, summary=f"创建代理 {result.username}", metadata=result.model_dump(mode="json"))
    return result


@router.get("/", response_model=AgentListResponse)
async def list_agents_endpoint(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=500), status_filter: str | None = Query(default=None, alias="status"), current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> AgentListResponse:
    return await list_agents(db=db, page=page, page_size=page_size, status_filter=status_filter)


@router.get("/tree", response_model=list[AgentSubtreeResponse])
async def get_full_agent_tree(current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> list[AgentSubtreeResponse]:
    result = await db.execute(select(Agent).where(Agent.parent_agent_id.is_(None)).order_by(Agent.id))
    return [await get_agent_subtree(agent.id, db) for agent in result.scalars().all()]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_endpoint(agent_id: int, current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> AgentResponse:
    return await get_agent(agent_id=agent_id, db=db)


@router.get("/{agent_id}/subtree", response_model=AgentSubtreeResponse)
async def get_agent_subtree_endpoint(agent_id: int, current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> AgentSubtreeResponse:
    return await get_agent_subtree(root_agent_id=agent_id, db=db)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent_endpoint(agent_id: int, body: AgentUpdateRequest, current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> AgentResponse:
    result = await update_agent(agent_id=agent_id, body=body, db=db)
    await create_audit_log(db=db, actor_type="admin", actor_id=current_admin.id, action="agent.update", target_type="agent", target_id=result.id, summary=f"更新代理 {result.username}", metadata={"agent_id": result.id, "username": result.username, "changed_fields": body.model_dump(exclude_unset=True), "status": result.status, "commission_rate": result.commission_rate})
    return result


@router.delete("/{agent_id}", summary="管理员硬删除代理")
async def delete_agent_endpoint(agent_id: int, current_admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_main_db)) -> dict:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在")

    blockers = await _get_agent_delete_blockers(db=db, agent_id=agent_id)
    if blockers:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "该代理存在业务关联，不能硬删除。请先迁移或清理关联数据。", "blockers": blockers})

    metadata = {"agent_id": agent.id, "username": agent.username, "parent_agent_id": agent.parent_agent_id, "hierarchy_depth": agent.hierarchy_depth, "status": agent.status}
    await create_audit_log(db=db, actor_type="admin", actor_id=current_admin.id, action="agent.hard_delete", target_type="agent", target_id=agent.id, summary=f"硬删除代理 {agent.username}", metadata=metadata)
    await db.delete(agent)
    await db.flush()
    return {"deleted": True, "agent_id": agent_id, "username": metadata["username"]}
