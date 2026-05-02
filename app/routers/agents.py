r"""
文件位置: app/routers/agents.py
文件名称: agents.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理管理路由（薄层）。

    ⚠️ 路由注册顺序规则：
      静态路径必须在参数化路径之前注册，否则 FastAPI 会把静态段当作参数解析。
      例如 /tree 必须在 /{agent_id} 之前，否则 FastAPI 会尝试把 "tree" 解析为 int。

    Phase 1（管理员操作）：
      POST  /api/agents/auth/login    代理登录
      GET   /api/agents/me            代理个人主页（Agent Token）
      POST  /api/agents/              创建代理（Admin Token）
      GET   /api/agents/              查询全部代理列表（Admin Token）
      GET   /api/agents/tree          全代理树（静态路径，必须在 /{id} 之前）
      GET   /api/agents/my-projects   代理已授权项目列表（Agent Token）
      GET   /api/agents/scope/list    代理权限范围内的下级列表（Agent Token）
      GET   /api/agents/{id}          查询代理详情（Admin Token）
      GET   /api/agents/{id}/subtree  查询代理子树（Admin Token）
      PATCH /api/agents/{id}          更新代理信息（Admin Token）

当前业务口径:
    - Agent.level 表示代理组织层级 / 代理树深度。
    - AgentBusinessProfile.tier_level 表示代理业务等级。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。

改进历史:
    V1.1.0 (2026-04-29) - 移除旧账号数量限制口径，保留用户数量统计。
    V1.0.3 (2026-04-26) - 新增 GET /api/agents/me 代理个人主页
    V1.0.2 (2026-04-25) - 修复路由顺序；恢复 my-projects 端点
    V1.0.1 (2026-04-25) - 新增 Phase 2 树形查询端点
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_agent
from app.database import get_main_db
from app.models.main.models import Admin, Agent, AgentProjectAuth, GameProject, User
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
from app.services.accounting_service import get_balance_transactions
from app.services.agent_service import (
    agent_login,
    create_agent,
    get_agent,
    get_agent_subtree,
    list_agents,
    list_agents_in_scope,
    update_agent,
)

router = APIRouter()


# ── 登录 ──────────────────────────────────────────────────────

@router.post("/auth/login", response_model=AgentLoginResponse)
async def agent_login_endpoint(
    body: AgentLoginRequest,
    db: AsyncSession = Depends(get_main_db),
) -> AgentLoginResponse:
    """代理登录，返回 Agent Token（有效期 8 小时）。"""
    return await agent_login(body=body, db=db)


# ── 代理个人主页（静态路径，必须在 /{agent_id} 之前）──────────

@router.get("/me", summary="代理个人主页")
async def get_my_profile(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """
    代理获取自己的详细个人信息（Agent Token）。

    返回：
      - 基本信息（用户名、组织层级、状态、创建时间）
      - 直属用户数统计（只统计，不再作为配额限制）
      - 已授权项目列表（含到期时间）
      - 上级代理信息（若有）
    """
    users_total = (await db.execute(
        select(func.count(User.id)).where(User.created_by_agent_id == current_agent.id)
    )).scalar_one()

    users_active = (await db.execute(
        select(func.count(User.id)).where(
            User.created_by_agent_id == current_agent.id,
            User.status == "active",
        )
    )).scalar_one()

    users_suspended = (await db.execute(
        select(func.count(User.id)).where(
            User.created_by_agent_id == current_agent.id,
            User.status == "suspended",
        )
    )).scalar_one()

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
    proj_rows = proj_result.all()
    now = datetime.now(tz=timezone.utc)

    authorized_projects = [
        {
            "id": project.id,
            "display_name": project.display_name,
            "code_name": project.code_name,
            "project_type": project.project_type,
            "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
            "is_expired": (
                auth.valid_until is not None
                and auth.valid_until.replace(tzinfo=timezone.utc) <= now
            ),
        }
        for auth, project in proj_rows
    ]

    parent_info = None
    if current_agent.parent_agent_id:
        parent = await db.get(Agent, current_agent.parent_agent_id)
        if parent:
            parent_info = {
                "id": parent.id,
                "username": parent.username,
                "level": parent.level,
            }

    return {
        "id": current_agent.id,
        "username": current_agent.username,
        "level": current_agent.level,
        "status": current_agent.status,
        "created_at": current_agent.created_at.isoformat(),
        "updated_at": current_agent.updated_at.isoformat() if current_agent.updated_at else None,
        "commission_rate": float(current_agent.commission_rate) if current_agent.commission_rate else None,
        "parent_agent": parent_info,
        "users_total": users_total,
        "users_active": users_active,
        "users_suspended": users_suspended,
        "authorized_projects": authorized_projects,
    }


# ── 代理流水查询（静态路径，原 balance_agent 迁移至此）─────────

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
    """代理查询自己的点数流水记录（Agent Token）。"""
    return await get_balance_transactions(
        agent_id=current_agent.id,
        db=db,
        page=page,
        page_size=page_size,
        tx_type=tx_type,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
    )


# ── 已授权项目列表（静态路径）────────────────────────────────

@router.get("/my-projects", response_model=list[dict])
async def get_my_authorized_projects(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    """
    代理获取自己已授权的项目列表（Agent Token）。
    用于前端在创建用户 / 用户项目授权时过滤可选项目。
    只返回 status=active 且未过期的项目授权。
    ⚠️ 必须在 /{agent_id} 之前注册。
    """
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
    rows = result.all()

    now = datetime.now(tz=timezone.utc)
    return [
        {
            "id": project.id,
            "display_name": project.display_name,
            "code_name": project.code_name,
            "project_type": project.project_type,
            "auth_valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
        }
        for auth, project in rows
        if auth.valid_until is None
        or auth.valid_until.replace(tzinfo=timezone.utc) > now
    ]


# ── 权限范围列表（静态路径）──────────────────────────────────

@router.get("/scope/list", response_model=AgentFlatListResponse)
async def list_agents_in_scope_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentFlatListResponse:
    """
    代理查看自己权限范围内的所有下级代理（Agent Token）。
    ⚠️ 此端点必须注册在 /{agent_id} 之前。
    """
    return await list_agents_in_scope(
        scope_agent_id=current_agent.id,
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )


# ── 创建 / 列表（Admin）──────────────────────────────────────

@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(
    body: AgentCreateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    """创建代理（需管理员身份）。"""
    return await create_agent(body=body, admin=current_admin, db=db)


@router.get("/", response_model=AgentListResponse)
async def list_agents_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentListResponse:
    """查询全部代理列表（管理员可见全部，支持状态过滤，分页）。"""
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
    """
    查询全部代理树（Admin Token）。
    ⚠️ 此端点必须注册在 /{agent_id} 之前。
    """
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
    """查询指定代理详情（含直属用户数统计）。"""
    return await get_agent(agent_id=agent_id, db=db)


@router.get("/{agent_id}/subtree", response_model=AgentSubtreeResponse)
async def get_agent_subtree_endpoint(
    agent_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentSubtreeResponse:
    """查询指定代理及其所有下级代理的树形结构（WITH RECURSIVE）。"""
    return await get_agent_subtree(root_agent_id=agent_id, db=db)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent_endpoint(
    agent_id: int,
    body: AgentUpdateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentResponse:
    """更新代理状态或佣金比例（需管理员身份）。"""
    return await update_agent(agent_id=agent_id, body=body, db=db)