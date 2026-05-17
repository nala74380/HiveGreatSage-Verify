r"""
文件位置: app/services/agent_service.py
文件名称: agent_service.py
作者: HiveGreatSage Dev
日期/时间: 2026-05-08
版本: V1.1.3
功能说明:
    代理管理及登录服务层，包含：
      - admin_login()           管理员登录，签发 Admin Token
      - agent_login()           代理登录，签发 Agent Token
      - create_agent()          创建代理（管理员调用）
      - list_agents()           查询代理列表（管理员，分页）
      - get_agent()             查询代理详情（含有效直属用户数统计）
      - update_agent()          更新代理状态/佣金
      ---- Phase 2 新增（WITH RECURSIVE）────────────────────────
      - get_agent_subtree()     获取某代理及其所有下级代理的树形结构
      - get_all_agent_ids_in_subtree()  获取子树内所有代理 ID（扁平列表，用于权限过滤）
      - list_agents_in_scope()  代理查看自己权限范围内的所有下级代理（分页）

    WITH RECURSIVE 查询说明（D007 决策）：
      PostgreSQL 的 WITH RECURSIVE 支持在 SQL 层面完成树的遍历，
      不需要在 Python 层多次查询，效率远高于 N+1 循环。
      查询结果为扁平列表（含 hierarchy_depth 字段），再由 Python 组装成树形结构。

当前业务口径:
    - Agent.hierarchy_depth 表示代理组织层级 / 代理树深度。
    - 数据库列名仍为 agent.level，ORM 属性名为 hierarchy_depth。
    - AgentBusinessProfile.tier_level 表示代理业务等级。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - 业务统计默认只统计未软删除用户。
    - 已软删除用户保留在数据库中用于审计，不进入代理业务统计。
    - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和授权扣点规则控制。
    - 代理列表接口必须返回 authorized_projects 的稳定项目展示字段，避免前端出现 undefined。

本版修复:
    V1.1.3:
      - list_agents() / list_agents_in_scope() 批量补齐 authorized_projects。
      - authorized_projects 统一返回 display_name / project_name / project_display_name。
      - 避免代理管理页面“已授权项目”列显示 undefined。
    V1.1.2:
      - 修复 _fetch_subtree_flat() 使用 result.mappings() 后仍按 row[2] 取值导致 500 的问题。
      - 修复 _build_tree() 对 dict row 继续使用 row[2] 的问题。
      - 新建子代理时统一使用 parent.hierarchy_depth，不再访问不存在/不稳定的 parent.level。

关联文档:
    [[01-网络验证系统/数据库设计]]
    [[01-网络验证系统/架构设计]]
    [[01-网络验证系统/代理业务画像与等级治理规则]]
    [[01-网络验证系统/代理点数计费与返点规则]]

改进历史:
    V1.1.3 (2026-05-08) - 代理列表批量返回稳定项目展示字段。
    V1.1.2 (2026-05-08) - 修复代理树 mapping row 读取错误。
    V1.1.1 (2026-04-30) - 代理用户统计排除已软删除用户。
    V1.1.0 (2026-04-29) - 移除旧账号数量限制口径，用户数量仅作统计。
    V1.0.1 (2026-04-25) - 新增 Phase 2 递归查询：get_agent_subtree /
                          get_all_agent_ids_in_subtree / list_agents_in_scope
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_admin_token,
    create_agent_token,
    hash_password,
    verify_password,
)
from app.core.redis_client import get_all_heartbeats_for_game
from app.core.utils import get_agent_scope_ids
from app.models.main.models import Admin, Agent, AgentProjectAuth, Authorization, GameProject, User
from app.schemas.agent import (
    AdminLoginRequest,
    AdminLoginResponse,
    AgentCreateRequest,
    AgentFlatListResponse,
    AgentListResponse,
    AgentLoginRequest,
    AgentLoginResponse,
    AgentResponse,
    AgentSubtreeResponse,
    AgentTreeNode,
    AgentUpdateRequest,
)
from app.schemas.agent_me import (
    AgentMeParentResponse,
    AgentMeProjectResponse,
    AgentMeResponse,
)
from app.services.accounting_service import get_agent_balance
from app.services.agent_profile_service import get_agent_business_profile_summary


# ─────────────────────────────────────────────────────────────
# 登录
# ─────────────────────────────────────────────────────────────

async def admin_login(
    body: AdminLoginRequest,
    db: AsyncSession,
) -> AdminLoginResponse:
    """管理员登录，签发 Admin Token（有效期 8 小时）。"""
    result = await db.execute(
        select(Admin).where(Admin.username == body.username)
    )
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账号已被停用",
        )

    token = create_admin_token(admin.id)

    return AdminLoginResponse(
        access_token=token,
        expires_in=settings.ADMIN_TOKEN_EXPIRE_HOURS * 3600,
        admin_id=admin.id,
        username=admin.username,
    )


async def agent_login(
    body: AgentLoginRequest,
    db: AsyncSession,
) -> AgentLoginResponse:
    """代理登录，签发 Agent Token（有效期 8 小时）。"""
    result = await db.execute(
        select(Agent).where(Agent.username == body.username)
    )
    agent = result.scalar_one_or_none()

    if not agent or not verify_password(body.password, agent.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if agent.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理账号已被停用",
        )

    token = create_agent_token(agent.id)

    return AgentLoginResponse(
        access_token=token,
        expires_in=settings.AGENT_TOKEN_EXPIRE_HOURS * 3600,
        agent_id=agent.id,
        username=agent.username,
        hierarchy_depth=agent.hierarchy_depth,
    )


# ─────────────────────────────────────────────────────────────
# 代理 CRUD（Phase 1，单级操作）
# ─────────────────────────────────────────────────────────────

async def create_agent(
    body: AgentCreateRequest,
    admin: Admin,
    db: AsyncSession,
) -> AgentResponse:
    """
    创建代理（仅管理员可调用）。

    规则:
      - parent_agent_id=None → 顶级代理，hierarchy_depth=1。
      - 指定父代理 → hierarchy_depth = parent.hierarchy_depth + 1。
      - 用户数量不再作为代理配额硬约束。
      - 新建代理只创建代理账号主体；业务等级通过 AgentBusinessProfile 管理。
    """
    await _assert_agent_username_unique(body.username, db)

    hierarchy_depth = 1
    if body.parent_agent_id is not None:
        parent = await _get_agent_or_404(body.parent_agent_id, db)
        hierarchy_depth = int(parent.hierarchy_depth) + 1

    agent = Agent(
        username=body.username,
        password_hash=hash_password(body.password),
        parent_agent_id=body.parent_agent_id,
        hierarchy_depth=hierarchy_depth,
        created_by_admin_id=admin.id,
        commission_rate=body.commission_rate,
        status="active",
    )

    db.add(agent)
    await db.flush()

    return await _agent_to_response(agent, db)


async def list_agents(
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: str | None,
) -> AgentListResponse:
    """查询代理列表（管理员可见全部代理，分页）。"""
    query = select(Agent)

    if status_filter:
        query = query.where(Agent.status == status_filter)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Agent.hierarchy_depth, Agent.id)
        .offset(offset)
        .limit(page_size)
    )
    agents = result.scalars().all()

    agent_ids = [a.id for a in agents]
    user_count_map = await _batch_user_counts(agent_ids, db)
    project_map = await _batch_authorized_projects(agent_ids, db)

    agent_responses = [
        AgentResponse(
            id=a.id,
            username=a.username,
            hierarchy_depth=int(a.hierarchy_depth),
            parent_agent_id=a.parent_agent_id,
            created_by_admin_id=a.created_by_admin_id,
            commission_rate=float(a.commission_rate) if a.commission_rate else None,
            status=a.status,
            created_at=a.created_at,
            updated_at=a.updated_at,
            users_count=user_count_map.get(a.id, 0),
            authorized_projects=project_map.get(a.id, []),
        )
        for a in agents
    ]

    return AgentListResponse(
        agents=agent_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_agent(
    agent_id: int,
    db: AsyncSession,
) -> AgentResponse:
    """查询代理详情（含有效直属用户数统计）。"""
    agent = await _get_agent_or_404(agent_id, db)
    return await _agent_to_response(agent, db)


async def get_agent_me_summary(
    agent: Agent,
    db: AsyncSession,
) -> AgentMeResponse:
    """查询代理资料与轻量业务能力摘要（/api/agents/me）。"""
    user_stats = await _get_agent_user_stats(agent.id, db)
    profile = await get_agent_business_profile_summary(agent_id=agent.id, db=db)
    authorized_projects = await _get_agent_me_authorized_projects(agent.id, db)
    parent_agent = await _get_agent_parent_summary(agent.parent_agent_id, db)

    return AgentMeResponse(
        id=agent.id,
        username=agent.username,
        hierarchy_depth=int(agent.hierarchy_depth),
        status=agent.status,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        commission_rate=float(agent.commission_rate) if agent.commission_rate is not None else None,
        parent_agent=parent_agent,
        users_total=user_stats["users_total"],
        users_active=user_stats["users_active"],
        users_suspended=user_stats["users_suspended"],
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
        can_auto_open_project=profile["can_auto_open_project"],
        auto_open_project_limit=profile["auto_open_project_limit"],
        review_priority=profile["review_priority"],
    )


async def get_agent_dashboard_summary(
    agent: Agent,
    db: AsyncSession,
    redis,
) -> dict:
    """查询代理端工作台聚合摘要（/api/agents/me/dashboard）。"""
    profile = await get_agent_business_profile_summary(agent_id=agent.id, db=db)
    wallet = await get_agent_balance(agent.id, db)
    user_stats = await _get_agent_user_stats(agent.id, db)
    projects = await _get_agent_dashboard_projects(agent.id, db)
    online_count = await _get_agent_dashboard_online_devices(
        projects=projects,
        agent_id=agent.id,
        db=db,
        redis=redis,
    )
    expiring_auths = await _get_agent_dashboard_expiring_auths(agent.id, db)
    sub_agents, sub_expiring_auths = await _get_agent_dashboard_subtree_sections(
        agent=agent,
        profile=profile,
        db=db,
    )

    return {
        "agent": {
            "username": agent.username,
            "hierarchy_depth": int(agent.hierarchy_depth),
            "tier_level": profile.get("tier_level", 1),
            "tier_name": profile.get("tier_name", ""),
            "risk_status": profile.get("risk_status", "normal"),
        },
        "wallet": wallet,
        "users": {
            "total": user_stats["users_total"],
            "active": user_stats["users_active"],
        },
        "online_devices": online_count,
        "projects": projects,
        "expiring_auths": expiring_auths,
        "sub_agents": sub_agents,
        "sub_expiring_auths": sub_expiring_auths,
    }


async def update_agent(
    agent_id: int,
    body: AgentUpdateRequest,
    db: AsyncSession,
) -> AgentResponse:
    """
    更新代理基础信息。

    当前仅允许:
      - status
      - commission_rate

    不再支持:
      - 旧账号数量限制
    """
    agent = await _get_agent_or_404(agent_id, db)

    if body.status is not None:
        agent.status = body.status

    if body.commission_rate is not None:
        agent.commission_rate = body.commission_rate

    await db.flush()
    await db.refresh(agent)

    return await _agent_to_response(agent, db)


# ─────────────────────────────────────────────────────────────
# Phase 2：WITH RECURSIVE 多级代理树形查询
# ─────────────────────────────────────────────────────────────

async def get_agent_subtree(
    root_agent_id: int,
    db: AsyncSession,
) -> AgentSubtreeResponse:
    """
    获取指定代理及其所有下级代理的树形结构（WITH RECURSIVE）。

    实现步骤：
      1. 用 WITH RECURSIVE 一次查询出子树内所有节点（扁平列表）。
      2. 批量查询各代理的有效直属用户数（一次 GROUP BY，避免 N+1）。
      3. 在 Python 层将扁平列表组装成嵌套树形结构。
      4. 递归计算每个节点的 subtree_user_count。

    时间复杂度：
      O(n) 次 SQL 操作 + O(n) Python 组装，n=子树节点数。
    """
    root = await _get_agent_or_404(root_agent_id, db)

    flat_rows = await _fetch_subtree_flat(root_agent_id, db)
    if not flat_rows:
        flat_rows = [
            {
                "id": root.id,
                "username": root.username,
                "hierarchy_depth": root.hierarchy_depth,
                "parent_agent_id": root.parent_agent_id,
                "status": root.status,
                "commission_rate": float(root.commission_rate) if root.commission_rate else None,
                "created_by_admin_id": root.created_by_admin_id,
                "created_at": root.created_at,
                "updated_at": root.updated_at,
            }
        ]

    all_ids = [row["id"] for row in flat_rows]
    user_count_map = await _batch_user_counts(all_ids, db)

    tree_root = _build_tree(
        flat_rows=flat_rows,
        root_id=root_agent_id,
        user_count_map=user_count_map,
    )

    total_agents = len(flat_rows)
    total_users = sum(user_count_map.get(aid, 0) for aid in all_ids)

    return AgentSubtreeResponse(
        root=tree_root,
        total_agents=total_agents,
        total_users=total_users,
    )


async def get_all_agent_ids_in_subtree(
    root_agent_id: int,
    db: AsyncSession,
) -> list[int]:
    """
    获取指定代理及其所有下级代理的 ID 列表。

    典型用途：
      代理查看权限范围内的用户时，先取得所有子代理 ID，
      再用 WHERE created_by_agent_id IN (...) 过滤。
    """
    return await get_agent_scope_ids(db, root_agent_id)


async def list_agents_in_scope(
    scope_agent_id: int,
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: str | None = None,
) -> AgentFlatListResponse:
    """
    代理查看自己权限范围内的所有下级代理（扁平分页列表）。

    权限规则：
      代理能看到自己 + 所有下级代理，不含平级或上级代理。
    """
    all_ids = await get_all_agent_ids_in_subtree(scope_agent_id, db)

    query = select(Agent).where(Agent.id.in_(all_ids))

    if status_filter:
        query = query.where(Agent.status == status_filter)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Agent.hierarchy_depth, Agent.id)
        .offset(offset)
        .limit(page_size)
    )
    agents = result.scalars().all()

    agent_ids = [a.id for a in agents]
    user_count_map = await _batch_user_counts(agent_ids, db)
    project_map = await _batch_authorized_projects(agent_ids, db)

    agent_responses = [
        AgentResponse(
            id=a.id,
            username=a.username,
            hierarchy_depth=int(a.hierarchy_depth),
            parent_agent_id=a.parent_agent_id,
            created_by_admin_id=a.created_by_admin_id,
            commission_rate=float(a.commission_rate) if a.commission_rate else None,
            status=a.status,
            created_at=a.created_at,
            updated_at=a.updated_at,
            users_count=user_count_map.get(a.id, 0),
            authorized_projects=project_map.get(a.id, []),
        )
        for a in agents
    ]

    return AgentFlatListResponse(
        agents=agent_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_agent_scope_list_enriched(
    *,
    scope_agent_id: int,
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: str | None = None,
) -> dict:
    """查询代理端权限范围超级列表，并补齐展示增强字段。"""
    result = await list_agents_in_scope(
        scope_agent_id=scope_agent_id,
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return await _enrich_scope_agent_list(db=db, result=result)


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_agent_or_404(
    agent_id: int,
    db: AsyncSession,
) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"代理 ID={agent_id} 不存在",
        )

    return agent


async def _assert_agent_username_unique(
    username: str,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(Agent).where(Agent.username == username)
    )

    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"代理用户名 '{username}' 已存在",
        )


async def _agent_to_response(
    agent: Agent,
    db: AsyncSession,
) -> AgentResponse:
    """将 Agent ORM 对象转换为 AgentResponse，附带有效直属用户数统计和项目授权。"""
    count_result = await db.execute(
        select(func.count(User.id)).where(
            User.created_by_agent_id == agent.id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    users_count = count_result.scalar_one()

    project_map = await _batch_authorized_projects([agent.id], db)

    return AgentResponse(
        id=agent.id,
        username=agent.username,
        hierarchy_depth=agent.hierarchy_depth,
        parent_agent_id=agent.parent_agent_id,
        created_by_admin_id=agent.created_by_admin_id,
        commission_rate=float(agent.commission_rate) if agent.commission_rate else None,
        status=agent.status,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        users_count=users_count,
        authorized_projects=project_map.get(agent.id, []),
    )


async def _get_agent_user_stats(
    agent_id: int,
    db: AsyncSession,
) -> dict[str, int]:
    users_total = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == agent_id
            )
        )
    ).scalar_one()

    users_active = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == agent_id,
                User.status == "active",
            )
        )
    ).scalar_one()

    users_suspended = (
        await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == agent_id,
                User.status == "suspended",
            )
        )
    ).scalar_one()

    return {
        "users_total": int(users_total or 0),
        "users_active": int(users_active or 0),
        "users_suspended": int(users_suspended or 0),
    }


async def _get_agent_me_authorized_projects(
    agent_id: int,
    db: AsyncSession,
) -> list[AgentMeProjectResponse]:
    proj_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.status == "active",
            GameProject.is_active == True,  # noqa: E712
        )
        .order_by(GameProject.display_name)
    )

    now = datetime.now(tz=timezone.utc)
    authorized_projects: list[AgentMeProjectResponse] = []

    for auth, project in proj_result.all():
        valid_until = auth.valid_until
        if valid_until is not None and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)

        authorized_projects.append(
            AgentMeProjectResponse(
                id=project.id,
                display_name=project.display_name,
                game_project_code=project.code_name,
                project_type=project.project_type,
                valid_until=valid_until,
                is_expired=valid_until is not None and valid_until <= now,
            )
        )

    return authorized_projects


async def _get_agent_parent_summary(
    parent_agent_id: int | None,
    db: AsyncSession,
) -> AgentMeParentResponse | None:
    if not parent_agent_id:
        return None

    parent = await db.get(Agent, parent_agent_id)
    if not parent:
        return None

    return AgentMeParentResponse(
        id=parent.id,
        username=parent.username,
        hierarchy_depth=int(parent.hierarchy_depth),
    )


async def _get_agent_dashboard_projects(
    agent_id: int,
    db: AsyncSession,
) -> list[dict]:
    proj_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.status == "active",
        )
        .order_by(GameProject.display_name)
    )

    direct_user_ids_result = await db.execute(
        select(User.id).where(User.created_by_agent_id == agent_id)
    )
    direct_user_ids = direct_user_ids_result.scalars().all()

    projects: list[dict] = []
    for _auth, project in proj_result.all():
        user_count = (await db.execute(
            select(func.count(Authorization.id)).where(
                Authorization.game_project_id == project.id,
                Authorization.status == "active",
                Authorization.user_id.in_(direct_user_ids),
            )
        )).scalar_one()
        projects.append({
            "project_id": project.id,
            "code": project.code_name,
            "display": project.display_name,
            "user_count": int(user_count or 0),
            "online": 0,
        })

    return projects


async def _get_agent_dashboard_online_devices(
    *,
    projects: list[dict],
    agent_id: int,
    db: AsyncSession,
    redis,
) -> int:
    direct_user_ids_result = await db.execute(
        select(User.id).where(User.created_by_agent_id == agent_id)
    )
    direct_user_ids = set(direct_user_ids_result.scalars().all())

    online_count = 0
    for project in projects:
        heartbeats = await get_all_heartbeats_for_game(redis, project["project_id"])
        project_online = sum(1 for hb in heartbeats if hb["user_id"] in direct_user_ids)
        project["online"] = project_online
        online_count += project_online

    return online_count


async def _get_agent_dashboard_expiring_auths(
    agent_id: int,
    db: AsyncSession,
) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
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
            User.created_by_agent_id == agent_id,
        )
        .order_by(Authorization.valid_until.asc())
        .limit(5)
    )
    return [
        {
            "user": user.username,
            "level": auth.user_level,
            "project": project.display_name,
            "days": max(1, (auth.valid_until - now).days + 1),
        }
        for auth, user, project in expiring_result.all()
    ]


async def _get_agent_dashboard_subtree_sections(
    *,
    agent: Agent,
    profile: dict,
    db: AsyncSession,
) -> tuple[dict, list[dict]]:
    sub_agents = {"can_create": profile.get("can_create_sub_agents", False), "list": []}
    sub_expiring: list[dict] = []

    if not profile.get("can_create_sub_agents"):
        return sub_agents, sub_expiring

    scope_ids = await get_all_agent_ids_in_subtree(agent.id, db)
    sub_scope_ids = [scope_id for scope_id in scope_ids if scope_id != agent.id]

    if sub_scope_ids:
        sub_result = await db.execute(
            select(Agent).where(Agent.id.in_(sub_scope_ids)).order_by(Agent.hierarchy_depth, Agent.id)
        )
        for sub in sub_result.scalars().all():
            sub_wallet = await get_agent_balance(sub.id, db)
            sub_users_result = await db.execute(
                select(func.count(User.id)).where(User.created_by_agent_id == sub.id)
            )
            sub_profile = await get_agent_business_profile_summary(agent_id=sub.id, db=db)
            sub_agents["list"].append({
                "id": sub.id,
                "username": sub.username,
                "hierarchy_depth": int(sub.hierarchy_depth),
                "tier_level": sub_profile.get("tier_level", 1),
                "tier_name": sub_profile.get("tier_name", "Lv.1"),
                "users": int(sub_users_result.scalar_one() or 0),
                "balance": sub_wallet.get("available_total", 0),
                "is_direct": sub.parent_agent_id == agent.id,
            })

        now = datetime.now(tz=timezone.utc)
        week_later = now + timedelta(days=7)
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
            .order_by(Authorization.valid_until.asc())
            .limit(5)
        )
        sub_expiring = [
            {
                "user": user.username,
                "level": auth.user_level,
                "project": project.display_name,
                "agent": sub_agent.username,
                "days": max(1, (auth.valid_until - now).days + 1),
            }
            for auth, user, project, sub_agent in sub_exp_result.all()
        ]

    return sub_agents, sub_expiring


async def _enrich_scope_agent_list(
    *,
    db: AsyncSession,
    result: AgentFlatListResponse,
) -> dict:
    """
    为代理端超级列表补齐业务画像、余额、授权项目直属用户数。

    返回 dict 而不是 AgentFlatListResponse，避免 response_model 过滤增强字段。
    """
    data = result.model_dump(mode="json")

    for item in data.get("agents", []):
        agent_id = int(item["id"])
        item["business_profile"] = await get_agent_business_profile_summary(
            agent_id=agent_id,
            db=db,
        )
        item["balance"] = await get_agent_balance(agent_id, db)

    data = await _fill_scope_authorized_project_user_counts(
        db=db,
        data=data,
    )

    return data


async def _fill_scope_authorized_project_user_counts(
    *,
    db: AsyncSession,
    data: dict,
) -> dict:
    """
    回填代理端 scope/list 的 authorized_projects[].user_count。

    统计口径：
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


async def _fetch_subtree_flat(
    root_agent_id: int,
    db: AsyncSession,
) -> list[dict]:
    """
    用 PostgreSQL WITH RECURSIVE 一次性获取子树所有节点。

    返回:
      字典列表，每条记录对应一个代理节点，包含构建树形结构所需字段。
      根节点本身也包含在结果中。
    """
    sql = text(
        """
        WITH RECURSIVE subtree AS (
            SELECT
                id,
                username,
                level AS hierarchy_depth,
                parent_agent_id,
                status,
                commission_rate,
                created_by_admin_id,
                created_at,
                updated_at
            FROM agent
            WHERE id = :root_id

            UNION ALL

            SELECT
                a.id,
                a.username,
                a.level AS hierarchy_depth,
                a.parent_agent_id,
                a.status,
                a.commission_rate,
                a.created_by_admin_id,
                a.created_at,
                a.updated_at
            FROM agent a
            INNER JOIN subtree s ON a.parent_agent_id = s.id
        )
        SELECT *
        FROM subtree
        ORDER BY hierarchy_depth, id
        """
    )

    result = await db.execute(sql, {"root_id": root_agent_id})
    rows = result.mappings().all()

    return [
        {
            "id": row["id"],
            "username": row["username"],
            "hierarchy_depth": int(row["hierarchy_depth"]),
            "parent_agent_id": row["parent_agent_id"],
            "status": row["status"],
            "commission_rate": float(row["commission_rate"]) if row["commission_rate"] else None,
            "created_by_admin_id": row["created_by_admin_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


async def _batch_user_counts(
    agent_ids: list[int],
    db: AsyncSession,
) -> dict[int, int]:
    """
    批量查询多个代理的有效直属用户数。

    返回:
      {agent_id: user_count}

    统计口径:
      - 只统计 User.is_deleted == False 的用户。
      - 已软删除用户保留审计，但不进入业务统计。
      - 用户数量只作为统计，不再作为代理配额限制。
    """
    if not agent_ids:
        return {}

    counts_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id))
        .where(
            User.created_by_agent_id.in_(agent_ids),
            User.is_deleted == False,  # noqa: E712
        )
        .group_by(User.created_by_agent_id)
    )

    return {
        agent_id: cnt
        for agent_id, cnt in counts_result.all()
    }


async def _batch_authorized_projects(
    agent_ids: list[int],
    db: AsyncSession,
) -> dict[int, list[dict]]:
    """
    批量查询多个代理的项目授权列表。

    设计目标:
      - 代理列表页避免 N+1 查询。
      - 对外字段稳定提供 display_name，避免前端显示 undefined。
      - 同时保留 project_name / project_display_name / project_code / game_project_code，
        方便不同页面逐步收敛到统一契约。
    """
    if not agent_ids:
        return {}

    auth_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id.in_(agent_ids))
        .order_by(AgentProjectAuth.agent_id, GameProject.display_name)
    )

    project_map: dict[int, list[dict]] = {agent_id: [] for agent_id in agent_ids}

    for auth, proj in auth_result.all():
        project_map.setdefault(auth.agent_id, []).append(
            {
                "id": proj.id,
                "project_id": proj.id,
                "display_name": proj.display_name,
                "project_display_name": proj.display_name,
                "project_name": proj.display_name,
                "code_name": proj.code_name,
                "project_code": proj.code_name,
                "game_project_code": proj.code_name,
                "project_type": proj.project_type,
                "status": auth.status,
                "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
                "granted_at": auth.granted_at.isoformat() if getattr(auth, "granted_at", None) else None,
                "source": auth.source,
                "user_count": 0,
            }
        )

    return project_map


def _build_tree(
    flat_rows: list[dict],
    root_id: int,
    user_count_map: dict[int, int],
) -> AgentTreeNode:
    """
    将 WITH RECURSIVE 查出的扁平列表组装为嵌套树形结构。

    算法:
      1. 先把所有节点转换为 AgentTreeNode，children 暂空。
      2. 遍历所有节点，把每个节点挂到其父节点的 children 上。
      3. 递归计算每个节点的 subtree_user_count。
    """
    node_map: dict[int, AgentTreeNode] = {}

    for row in flat_rows:
        node_map[row["id"]] = AgentTreeNode(
            id=row["id"],
            username=row["username"],
            hierarchy_depth=int(row["hierarchy_depth"]),
            parent_agent_id=row["parent_agent_id"],
            status=row["status"],
            commission_rate=row["commission_rate"],
            users_count=user_count_map.get(row["id"], 0),
            subtree_user_count=user_count_map.get(row["id"], 0),
            children=[],
        )

    for row in flat_rows:
        node = node_map[row["id"]]
        parent_id = row["parent_agent_id"]

        if parent_id is not None and parent_id in node_map:
            node_map[parent_id].children.append(node)

    _accumulate_subtree_count(node_map[root_id])

    return node_map[root_id]


def _accumulate_subtree_count(
    node: AgentTreeNode,
) -> int:
    """
    递归计算 subtree_user_count。

    subtree_user_count =
      当前代理有效直属用户数 + 所有子代理 subtree_user_count 之和
    """
    total = node.users_count

    for child in node.children:
        total += _accumulate_subtree_count(child)

    node.subtree_user_count = total

    return total
