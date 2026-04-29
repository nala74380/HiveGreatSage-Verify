r"""
文件位置: app/services/stats_service.py
名称: 统计聚合服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.0.0
功能说明:
    提供用户、代理、平台维度的统计聚合查询。
    全部使用单次 SQL 聚合（GROUP BY），不做 N+1 查询。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import (
    Agent, Authorization, DeviceBinding, GameProject, User
)
from app.schemas.stats import (
    AgentProjectSummaryResponse,
    DeviceStatsByProject,
    PlatformSummaryResponse,
    ProjectUserCount,
    UserProjectStatsResponse,
)
from app.services.agent_service import get_all_agent_ids_in_subtree


async def get_user_project_stats(
    user_id: int,
    db: AsyncSession,
) -> UserProjectStatsResponse:
    """
    查询某用户在各游戏项目下的设备绑定/激活统计。

    单次联表查询：
      authorization LEFT JOIN game_project
      device_binding GROUP BY game_project_id
    """
    # 查该用户所有授权
    auth_result = await db.execute(
        select(Authorization, GameProject)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(Authorization.user_id == user_id)
        .order_by(Authorization.id)
    )
    auth_rows = auth_result.all()

    # 批量查设备绑定统计（一次 GROUP BY，不循环查）
    project_ids = [r.Authorization.game_project_id for r in auth_rows]
    device_stats: dict[int, dict] = {}
    if project_ids:
        # device_binding 目前不含 game_project_id，是全局绑定
        # 激活状态以 imsi IS NOT NULL 或未来新增 activated 字段为准
        # Phase 1 暂以 status='active' 计总绑定，imsi 非空计激活
        total_result = await db.execute(
            select(func.count(DeviceBinding.id))
            .where(
                DeviceBinding.user_id == user_id,
                DeviceBinding.status == "active",
            )
        )
        total_bound = total_result.scalar_one()

        activated_result = await db.execute(
            select(func.count(DeviceBinding.id))
            .where(
                DeviceBinding.user_id == user_id,
                DeviceBinding.status == "active",
                DeviceBinding.imsi.is_not(None),
            )
        )
        activated = activated_result.scalar_one()
    else:
        total_bound = 0
        activated   = 0

    not_activated = total_bound - activated

    project_stats = []
    for row in auth_rows:
        auth    = row.Authorization
        project = row.GameProject
        # 当前每用户的设备绑定是全局的（不区分项目），
        # Phase 2 可按项目拆分（device_binding 加 game_project_id 字段后）
        ps = DeviceStatsByProject(
            game_project_id=project.id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            authorization_status=auth.status,
            valid_until=auth.valid_until,
            total_bound=total_bound,
            activated=activated,
            not_activated=not_activated,
            online_now=0,   # Redis 实时值由路由层注入（可选）
        )
        project_stats.append(ps)

    # 查用户基本信息
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    active_projects = sum(1 for p in project_stats if p.authorization_status == "active")

    return UserProjectStatsResponse(
        user_id=user_id,
        username=user.username if user else str(user_id),
        user_level=user.user_level if user else "",
        project_stats=project_stats,
        total_projects=len(project_stats),
        active_projects=active_projects,
        total_devices_bound=total_bound,
        total_activated=activated,
        total_not_activated=not_activated,
    )


async def get_agent_project_summary(
    agent_id: int,
    db: AsyncSession,
) -> AgentProjectSummaryResponse:
    """
    代理视角：我的权限范围内各项目的用户/授权/设备统计。

    步骤：
      1. WITH RECURSIVE 获取所有下级代理 ID
      2. 查这些代理创建的用户
      3. 按 game_project GROUP BY 聚合授权和设备数
    """
    # 获取权限范围内所有代理 ID
    scope_agent_ids = await get_all_agent_ids_in_subtree(agent_id, db)

    # 权限范围内所有用户 ID
    user_result = await db.execute(
        select(User.id).where(
            User.created_by_agent_id.in_(scope_agent_ids),
            User.status == "active",
        )
    )
    user_ids = [r[0] for r in user_result.all()]
    scope_user_count = len(user_ids)

    # 代理总数
    scope_agent_count = len(scope_agent_ids)

    if not user_ids:
        agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        return AgentProjectSummaryResponse(
            agent_id=agent_id,
            agent_username=agent.username if agent else str(agent_id),
            scope_agent_count=scope_agent_count,
            scope_user_count=0,
            project_summaries=[],
        )

    # 按项目聚合授权数
    auth_agg_result = await db.execute(
        select(
            Authorization.game_project_id,
            func.count(Authorization.id).label("auth_count"),
            func.sum(
                (Authorization.status == "active").cast(db.bind.dialect.BOOLEAN)
                if hasattr(db, 'bind') else Authorization.status
            ).label("active_auth_count"),
        )
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.game_project_id)
    )

    # 简化版：分两次查
    auth_total_result = await db.execute(
        select(
            Authorization.game_project_id,
            func.count(Authorization.id).label("total"),
        )
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.game_project_id)
    )
    auth_active_result = await db.execute(
        select(
            Authorization.game_project_id,
            func.count(Authorization.id).label("active"),
        )
        .where(
            Authorization.user_id.in_(user_ids),
            Authorization.status == "active",
        )
        .group_by(Authorization.game_project_id)
    )

    total_map  = {r.game_project_id: r.total  for r in auth_total_result.all()}
    active_map = {r.game_project_id: r.active for r in auth_active_result.all()}

    # 按项目用户数
    user_per_project_result = await db.execute(
        select(
            Authorization.game_project_id,
            func.count(func.distinct(Authorization.user_id)).label("user_count"),
        )
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.game_project_id)
    )
    user_count_map = {r.game_project_id: r.user_count for r in user_per_project_result.all()}

    # 设备统计
    device_total_result = await db.execute(
        select(func.count(DeviceBinding.id))
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
        )
    )
    total_devices = device_total_result.scalar_one()

    device_activated_result = await db.execute(
        select(func.count(DeviceBinding.id))
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
            DeviceBinding.imsi.is_not(None),
        )
    )
    activated_devices = device_activated_result.scalar_one()

    # 查项目名
    project_ids = list(total_map.keys())
    projects_result = await db.execute(
        select(GameProject).where(GameProject.id.in_(project_ids))
    )
    projects = {p.id: p for p in projects_result.scalars().all()}

    summaries = []
    for pid in project_ids:
        proj = projects.get(pid)
        if not proj:
            continue
        summaries.append(ProjectUserCount(
            game_project_id=pid,
            game_project_code=proj.code_name,
            game_project_name=proj.display_name,
            user_count=user_count_map.get(pid, 0),
            authorization_count=total_map.get(pid, 0),
            active_authorization_count=active_map.get(pid, 0),
            total_devices=total_devices,
            activated_devices=activated_devices,
        ))

    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    return AgentProjectSummaryResponse(
        agent_id=agent_id,
        agent_username=agent.username if agent else str(agent_id),
        scope_agent_count=scope_agent_count,
        scope_user_count=scope_user_count,
        project_summaries=summaries,
    )


async def get_platform_summary(db: AsyncSession) -> PlatformSummaryResponse:
    """管理员全平台概览统计（首页 Dashboard）。"""
    total_users   = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users  = (await db.execute(
        select(func.count(User.id)).where(User.status == "active")
    )).scalar_one()
    total_agents  = (await db.execute(select(func.count(Agent.id)))).scalar_one()
    total_proj    = (await db.execute(
        select(func.count(GameProject.id)).where(GameProject.is_active == True)
    )).scalar_one()
    total_devices = (await db.execute(
        select(func.count(DeviceBinding.id)).where(DeviceBinding.status == "active")
    )).scalar_one()
    total_auth    = (await db.execute(select(func.count(Authorization.id)))).scalar_one()

    # 按级别分布
    level_result = await db.execute(
        select(User.user_level, func.count(User.id))
        .group_by(User.user_level)
    )
    level_dist = {row[0]: row[1] for row in level_result.all()}

    return PlatformSummaryResponse(
        total_users=total_users,
        active_users=active_users,
        total_agents=total_agents,
        total_projects=total_proj,
        total_devices_bound=total_devices,
        total_devices_online=0,   # 路由层从 Redis 注入
        total_authorizations=total_auth,
        level_distribution=level_dist,
    )
