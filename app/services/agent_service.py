r"""
文件位置: app/services/agent_service.py
文件名称: agent_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理管理及登录服务层，包含：
      - admin_login()           管理员登录，签发 Admin Token
      - agent_login()           代理登录，签发 Agent Token
      - create_agent()          创建代理（管理员调用）
      - list_agents()           查询代理列表（管理员，分页）
      - get_agent()             查询代理详情（含用户数统计）
      - update_agent()          更新代理状态/佣金
      ---- Phase 2 新增（WITH RECURSIVE）────────────────────────
      - get_agent_subtree()     获取某代理及其所有下级代理的树形结构
      - get_all_agent_ids_in_subtree()  获取子树内所有代理 ID（扁平列表，用于权限过滤）
      - list_agents_in_scope()  代理查看自己权限范围内的所有下级代理（分页）

    WITH RECURSIVE 查询说明（D007 决策）：
      PostgreSQL 的 WITH RECURSIVE 支持在 SQL 层面完成树的遍历，
      不需要在 Python 层多次查询，效率远高于 N+1 循环。
      查询结果为扁平列表（含 depth 字段），再由 Python 组装成树形结构。

当前业务口径:
    - Agent.level 表示代理组织层级 / 代理树深度。
    - AgentBusinessProfile.tier_level 表示代理业务等级。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。

关联文档:
    [[01-网络验证系统/数据库设计]]
    [[01-网络验证系统/架构设计]]
    [[01-网络验证系统/代理业务画像与等级治理规则]]
    [[01-网络验证系统/代理点数计费与返点规则]]

改进历史:
    V1.1.0 (2026-04-29) - 移除旧账号数量限制口径，用户数量仅作统计。
    V1.0.1 (2026-04-25) - 新增 Phase 2 递归查询：get_agent_subtree /
                          get_all_agent_ids_in_subtree / list_agents_in_scope
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

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
from app.models.main.models import Admin, Agent, User
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
        level=agent.level,
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
      - parent_agent_id=None → 顶级代理，level=1。
      - 指定父代理 → level = parent.level + 1。
      - 用户数量不再作为代理配额硬约束。
      - 新建代理只创建代理账号主体；业务等级通过 AgentBusinessProfile 管理。
    """
    await _assert_agent_username_unique(body.username, db)

    level = 1
    if body.parent_agent_id is not None:
        parent = await _get_agent_or_404(body.parent_agent_id, db)
        level = parent.level + 1

    agent = Agent(
        username=body.username,
        password_hash=hash_password(body.password),
        parent_agent_id=body.parent_agent_id,
        level=level,
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
        query.order_by(Agent.level, Agent.id)
        .offset(offset)
        .limit(page_size)
    )
    agents = result.scalars().all()

    agent_ids = [a.id for a in agents]
    user_count_map = await _batch_user_counts(agent_ids, db)

    agent_responses = [
        AgentResponse(
            id=a.id,
            username=a.username,
            level=a.level,
            parent_agent_id=a.parent_agent_id,
            created_by_admin_id=a.created_by_admin_id,
            commission_rate=float(a.commission_rate) if a.commission_rate else None,
            status=a.status,
            created_at=a.created_at,
            updated_at=a.updated_at,
            users_count=user_count_map.get(a.id, 0),
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
    """查询代理详情（含直接创建的用户数统计）。"""
    agent = await _get_agent_or_404(agent_id, db)
    return await _agent_to_response(agent, db)


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
      2. 批量查询各代理的直属用户数（一次 GROUP BY，避免 N+1）。
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
                "level": root.level,
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
    flat_rows = await _fetch_subtree_flat(root_agent_id, db)
    ids = [row["id"] for row in flat_rows]

    if root_agent_id not in ids:
        ids.insert(0, root_agent_id)

    return ids


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
        query.order_by(Agent.level, Agent.id)
        .offset(offset)
        .limit(page_size)
    )
    agents = result.scalars().all()

    agent_ids = [a.id for a in agents]
    user_count_map = await _batch_user_counts(agent_ids, db)

    agent_responses = [
        AgentResponse(
            id=a.id,
            username=a.username,
            level=a.level,
            parent_agent_id=a.parent_agent_id,
            created_by_admin_id=a.created_by_admin_id,
            commission_rate=float(a.commission_rate) if a.commission_rate else None,
            status=a.status,
            created_at=a.created_at,
            updated_at=a.updated_at,
            users_count=user_count_map.get(a.id, 0),
        )
        for a in agents
    ]

    return AgentFlatListResponse(
        agents=agent_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


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
    """将 Agent ORM 对象转换为 AgentResponse，附带直属用户数统计。"""
    count_result = await db.execute(
        select(func.count(User.id)).where(User.created_by_agent_id == agent.id)
    )
    users_count = count_result.scalar_one()

    return AgentResponse(
        id=agent.id,
        username=agent.username,
        level=agent.level,
        parent_agent_id=agent.parent_agent_id,
        created_by_admin_id=agent.created_by_admin_id,
        commission_rate=float(agent.commission_rate) if agent.commission_rate else None,
        status=agent.status,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        users_count=users_count,
    )


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
                level,
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
                a.level,
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
        ORDER BY level, id
        """
    )

    result = await db.execute(sql, {"root_id": root_agent_id})
    rows = result.mappings().all()

    return [
        {
            "id": row["id"],
            "username": row["username"],
            "level": row["level"],
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
    批量查询多个代理的直属用户数。

    返回:
      {agent_id: user_count}

    注意:
      用户数量只作为统计，不再作为代理配额限制。
    """
    if not agent_ids:
        return {}

    counts_result = await db.execute(
        select(User.created_by_agent_id, func.count(User.id))
        .where(User.created_by_agent_id.in_(agent_ids))
        .group_by(User.created_by_agent_id)
    )

    return {
        agent_id: cnt
        for agent_id, cnt in counts_result.all()
    }


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
            level=row["level"],
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
      当前代理直属用户数 + 所有子代理 subtree_user_count 之和
    """
    total = node.users_count

    for child in node.children:
        total += _accumulate_subtree_count(child)

    node.subtree_user_count = total

    return total