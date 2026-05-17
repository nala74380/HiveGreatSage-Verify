r"""
文件位置: app/services/stats_service.py
名称: 统计聚合服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.1.0
功能说明:
    提供用户、代理、平台维度的统计聚合查询。
    全部使用聚合 SQL，避免 N+1 查询。

当前口径:
    - DeviceBinding 已按 user_id + game_project_id + device_fingerprint 建模。
    - 用户 / 代理项目统计中的设备数必须按项目维度聚合，不能再按用户全局绑定数复用到每个项目。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_all_heartbeats_for_game
from app.models.main.accounting import AccountingLedgerEntry, AccountingWallet
from app.models.main.models import (
    Admin, Agent, Authorization, DeviceBinding, GameProject, User
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

    口径:
      - 先查该用户所有 Authorization × GameProject。
      - 设备统计按 DeviceBinding.game_project_id 分项目聚合。
      - 每个项目项只返回该项目自己的绑定 / 激活设备数。
    """
    auth_result = await db.execute(
        select(Authorization, GameProject)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(Authorization.user_id == user_id)
        .order_by(Authorization.id)
    )
    auth_rows = auth_result.all()

    project_ids = [row.Authorization.game_project_id for row in auth_rows]

    device_total_map: dict[int, int] = {}
    device_activated_map: dict[int, int] = {}

    if project_ids:
        total_result = await db.execute(
            select(
                DeviceBinding.game_project_id,
                func.count(DeviceBinding.id).label("total_bound"),
            )
            .where(
                DeviceBinding.user_id == user_id,
                DeviceBinding.status == "active",
                DeviceBinding.game_project_id.in_(project_ids),
            )
            .group_by(DeviceBinding.game_project_id)
        )
        device_total_map = {
            int(project_id): int(total_bound)
            for project_id, total_bound in total_result.all()
            if project_id is not None
        }

        activated_result = await db.execute(
            select(
                DeviceBinding.game_project_id,
                func.count(DeviceBinding.id).label("activated"),
            )
            .where(
                DeviceBinding.user_id == user_id,
                DeviceBinding.status == "active",
                DeviceBinding.imsi_hash.is_not(None),
                DeviceBinding.game_project_id.in_(project_ids),
            )
            .group_by(DeviceBinding.game_project_id)
        )
        device_activated_map = {
            int(project_id): int(activated)
            for project_id, activated in activated_result.all()
            if project_id is not None
        }

    project_stats = []
    total_bound_all = 0
    total_activated_all = 0

    for row in auth_rows:
        auth = row.Authorization
        project = row.GameProject
        total_bound = device_total_map.get(project.id, 0)
        activated = device_activated_map.get(project.id, 0)
        not_activated = max(total_bound - activated, 0)

        total_bound_all += total_bound
        total_activated_all += activated

        project_stats.append(DeviceStatsByProject(
            game_project_id=project.id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            authorization_status=auth.status,
            valid_until=auth.valid_until,
            total_bound=total_bound,
            activated=activated,
            not_activated=not_activated,
            online_now=0,
        ))

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    active_projects = sum(1 for p in project_stats if p.authorization_status == "active")

    return UserProjectStatsResponse(
        user_id=user_id,
        username=user.username if user else str(user_id),
        project_stats=project_stats,
        total_projects=len(project_stats),
        active_projects=active_projects,
        total_devices_bound=total_bound_all,
        total_activated=total_activated_all,
        total_not_activated=max(total_bound_all - total_activated_all, 0),
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
      4. 设备统计按 DeviceBinding.game_project_id 分项目聚合
    """
    scope_agent_ids = await get_all_agent_ids_in_subtree(agent_id, db)

    user_result = await db.execute(
        select(User.id).where(
            User.created_by_agent_id.in_(scope_agent_ids),
            User.status == "active",
        )
    )
    user_ids = [row[0] for row in user_result.all()]
    scope_user_count = len(user_ids)
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

    total_map = {
        int(game_project_id): int(total)
        for game_project_id, total in auth_total_result.all()
        if game_project_id is not None
    }
    active_map = {
        int(game_project_id): int(active)
        for game_project_id, active in auth_active_result.all()
        if game_project_id is not None
    }

    user_per_project_result = await db.execute(
        select(
            Authorization.game_project_id,
            func.count(func.distinct(Authorization.user_id)).label("user_count"),
        )
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.game_project_id)
    )
    user_count_map = {
        int(game_project_id): int(user_count)
        for game_project_id, user_count in user_per_project_result.all()
        if game_project_id is not None
    }

    device_total_result = await db.execute(
        select(
            DeviceBinding.game_project_id,
            func.count(DeviceBinding.id).label("total_devices"),
        )
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
        )
        .group_by(DeviceBinding.game_project_id)
    )
    device_total_map = {
        int(game_project_id): int(total_devices)
        for game_project_id, total_devices in device_total_result.all()
        if game_project_id is not None
    }

    device_activated_result = await db.execute(
        select(
            DeviceBinding.game_project_id,
            func.count(DeviceBinding.id).label("activated_devices"),
        )
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
            DeviceBinding.imsi_hash.is_not(None),
        )
        .group_by(DeviceBinding.game_project_id)
    )
    device_activated_map = {
        int(game_project_id): int(activated_devices)
        for game_project_id, activated_devices in device_activated_result.all()
        if game_project_id is not None
    }

    project_ids = list(total_map.keys())
    projects_result = await db.execute(
        select(GameProject).where(GameProject.id.in_(project_ids))
    )
    projects = {project.id: project for project in projects_result.scalars().all()}

    summaries = []
    for project_id in project_ids:
        project = projects.get(project_id)
        if not project:
            continue
        summaries.append(ProjectUserCount(
            game_project_id=project_id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            user_count=user_count_map.get(project_id, 0),
            authorization_count=total_map.get(project_id, 0),
            active_authorization_count=active_map.get(project_id, 0),
            total_devices=device_total_map.get(project_id, 0),
            activated_devices=device_activated_map.get(project_id, 0),
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


async def get_platform_summary(
    db: AsyncSession,
    redis,
) -> PlatformSummaryResponse:
    """管理员全平台标准摘要统计（/api/stats/platform）。"""
    total_users = (await db.execute(
        select(func.count(User.id)).where(User.is_deleted == False)  # noqa: E712
    )).scalar_one()
    active_users = (await db.execute(
        select(func.count(User.id)).where(
            User.status == "active",
            User.is_deleted == False,  # noqa: E712
        )
    )).scalar_one()
    total_agents = (await db.execute(select(func.count(Agent.id)))).scalar_one()
    total_proj = (await db.execute(
        select(func.count(GameProject.id)).where(GameProject.is_active == True)
    )).scalar_one()
    total_devices = (await db.execute(
        select(func.count(DeviceBinding.id)).where(DeviceBinding.status == "active")
    )).scalar_one()
    total_auth = (await db.execute(select(func.count(Authorization.id)))).scalar_one()

    level_result = await db.execute(
        select(Authorization.user_level, func.count(Authorization.id))
        .group_by(Authorization.user_level)
    )
    level_dist = {row[0]: row[1] for row in level_result.all()}
    online_devices = await _get_platform_online_device_count(db=db, redis=redis)

    return PlatformSummaryResponse(
        total_users=total_users,
        active_users=active_users,
        total_agents=total_agents,
        total_projects=total_proj,
        total_devices_bound=total_devices,
        total_devices_online=online_devices,
        total_authorizations=total_auth,
        authorization_level_distribution=level_dist,
    )


async def _get_platform_online_device_count(
    *,
    db: AsyncSession,
    redis,
) -> int:
    try:
        projects = (await db.execute(
            select(GameProject).where(GameProject.is_active == True)
        )).scalars().all()

        online_count = 0
        for project in projects:
            heartbeats = await get_all_heartbeats_for_game(redis, project.id)
            online_count += len(heartbeats)

        return online_count
    except Exception:
        return 0


async def get_admin_dashboard_summary(
    *,
    current_admin: Admin,
    db: AsyncSession,
    redis,
) -> dict:
    """管理员工作台聚合摘要（/admin/api/dashboard）。"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    base_counts = await _get_admin_dashboard_base_counts(db=db, today_start=today_start)
    points_summary = await _get_admin_dashboard_points_summary(db=db)
    today_accounting = await _get_admin_dashboard_today_accounting(db=db, today_start=today_start)
    level_distribution = await _get_admin_dashboard_level_distribution(db=db)
    expiring_auths = await _get_admin_dashboard_expiring_auths(db=db, now=now)
    online_devices, active_projects_data = await _get_admin_dashboard_online_and_projects(db=db, redis=redis)
    system_health = await _get_admin_dashboard_system_health(redis=redis)

    return {
        "admin": current_admin.username,
        "total_users": base_counts["total_users"],
        "total_agents": base_counts["total_agents"],
        "active_projects": base_counts["active_projects"],
        "today_new_users": base_counts["today_new_users"],
        "total_points": points_summary["total_points"],
        "today_accounting": today_accounting,
        "refundable_wallets": points_summary["refundable_wallets"],
        "level_distribution": level_distribution,
        "expiring_auths": expiring_auths,
        "online_devices": online_devices,
        "active_projects_data": active_projects_data,
        "system_health": system_health,
    }


async def _get_admin_dashboard_base_counts(
    *,
    db: AsyncSession,
    today_start: datetime,
) -> dict:
    total_users = (await db.execute(
        select(func.count(User.id)).where(User.is_deleted == False)  # noqa: E712
    )).scalar_one()
    total_agents = (await db.execute(select(func.count(Agent.id)))).scalar_one()
    active_projects = (await db.execute(
        select(func.count(GameProject.id)).where(GameProject.is_active == True)
    )).scalar_one()
    today_new_users = (await db.execute(
        select(func.count(User.id)).where(
            User.is_deleted == False,  # noqa: E712
            User.created_at >= today_start,
        )
    )).scalar_one()

    return {
        "total_users": int(total_users or 0),
        "total_agents": int(total_agents or 0),
        "active_projects": int(active_projects or 0),
        "today_new_users": int(today_new_users or 0),
    }


async def _get_admin_dashboard_points_summary(
    *,
    db: AsyncSession,
) -> dict:
    wallet_totals = (await db.execute(
        select(
            func.coalesce(func.sum(AccountingWallet.charged_balance), 0),
            func.coalesce(func.sum(AccountingWallet.credit_balance), 0),
            func.coalesce(func.sum(AccountingWallet.frozen_credit), 0),
        )
    )).one()
    total_charged, total_credit, total_frozen = wallet_totals
    total_points = float(total_charged or 0) + float(total_credit or 0) - float(total_frozen or 0)

    refundable_wallets = (await db.execute(
        select(func.count(AccountingWallet.id)).where(
            AccountingWallet.available_total > 0,
        )
    )).scalar_one()

    return {
        "total_points": round(total_points, 2),
        "refundable_wallets": int(refundable_wallets or 0),
    }


async def _get_admin_dashboard_today_accounting(
    *,
    db: AsyncSession,
    today_start: datetime,
) -> dict:
    today_ledger = (await db.execute(
        select(
            AccountingLedgerEntry.entry_type,
            func.coalesce(func.sum(AccountingLedgerEntry.amount), 0),
        )
        .where(AccountingLedgerEntry.posted_at >= today_start)
        .group_by(AccountingLedgerEntry.entry_type)
    )).all()
    return {row[0]: float(row[1]) for row in today_ledger}


async def _get_admin_dashboard_level_distribution(
    *,
    db: AsyncSession,
) -> dict:
    level_rows = (await db.execute(
        select(Authorization.user_level, func.count(func.distinct(Authorization.user_id)))
        .where(Authorization.status == "active")
        .group_by(Authorization.user_level)
    )).all()
    return {row[0]: row[1] for row in level_rows}


async def _get_admin_dashboard_expiring_auths(
    *,
    db: AsyncSession,
    now: datetime,
) -> list[dict]:
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
        )
        .order_by(Authorization.valid_until.asc())
        .limit(5)
    )
    return [
        {
            "auth_id": auth.id,
            "user_id": user.id,
            "username": user.username,
            "project": project.display_name,
            "user_level": auth.user_level,
            "valid_until": auth.valid_until.isoformat(),
        }
        for auth, user, project in expiring_result.all()
    ]


async def _get_admin_dashboard_online_and_projects(
    *,
    db: AsyncSession,
    redis,
) -> tuple[int, list[dict]]:
    try:
        from app.core.redis_client import get_all_heartbeats_for_game

        online_count = 0
        active_projects = (await db.execute(
            select(GameProject).where(GameProject.is_active == True)
        )).scalars().all()
        active_projects_data = []
        for project in active_projects:
            heartbeats = await get_all_heartbeats_for_game(redis, project.id)
            project_online_count = len(heartbeats)
            online_count += project_online_count
            active_projects_data.append({
                "code": project.code_name,
                "display": project.display_name,
                "online_count": project_online_count,
            })
        return online_count, active_projects_data
    except Exception:
        return 0, []


async def _get_admin_dashboard_system_health(
    *,
    redis,
) -> dict:
    health = {"api": "ok", "database": "ok", "redis": "error", "celery": "unknown"}

    try:
        pong = await redis.ping()
        if pong:
            health["redis"] = "ok"
    except Exception:
        pass

    try:
        last_flush = await redis.get("health:last_heartbeat_flush")
        health["celery"] = "ok" if last_flush == "ok" else "no_recent_flush"
    except Exception:
        health["celery"] = "unknown"

    return health
