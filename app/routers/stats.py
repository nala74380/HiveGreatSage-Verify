r"""
文件位置: app/routers/stats.py
名称: 统计聚合路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.0.0
功能说明:
    统计相关端点（薄路由层）：

    GET /api/stats/users/{user_id}/projects   用户×项目设备激活统计
    GET /api/stats/agents/my/summary          代理权限范围内项目统计
    GET /admin/api/stats/platform             全平台概览（管理员）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_agent
from app.core.redis_client import get_redis
from app.database import get_main_db
from app.models.main.models import Admin, Agent
from app.schemas.stats import (
    AgentProjectSummaryResponse,
    PlatformSummaryResponse,
    UserProjectStatsResponse,
)
from app.services.stats_service import (
    get_agent_project_summary,
    get_platform_summary,
    get_user_project_stats,
)

router = APIRouter()


@router.get("/users/{user_id}/projects", response_model=UserProjectStatsResponse)
async def user_project_stats(
    user_id: int,
    db: AsyncSession = Depends(get_main_db),
    _admin: Admin = Depends(get_current_admin),
) -> UserProjectStatsResponse:
    """
    用户×项目维度的设备绑定/激活统计。
    回答：该用户被授权了哪些项目？每个项目绑定了多少设备？激活多少/未激活多少？
    """
    return await get_user_project_stats(user_id=user_id, db=db)


@router.get("/agents/my/summary", response_model=AgentProjectSummaryResponse)
async def agent_project_summary(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectSummaryResponse:
    """
    代理视角：我的权限范围内各项目的用户/授权/设备统计。
    回答：我下面有哪些项目？哪个项目多少用户？授权多少？设备多少？
    """
    return await get_agent_project_summary(agent_id=current_agent.id, db=db)


@router.get("/platform", response_model=PlatformSummaryResponse)
async def platform_summary(
    db: AsyncSession = Depends(get_main_db),
    redis = Depends(get_redis),
    _admin: Admin = Depends(get_current_admin),
) -> PlatformSummaryResponse:
    """
    全平台概览统计（管理员 Dashboard）。
    回答：全平台多少用户/代理/项目/设备？各级别分布？
    """
    result = await get_platform_summary(db=db)

    # 注入 Redis 实时在线设备数
    try:
        from app.core.redis_client import get_all_heartbeats_for_game
        # 简化：计算所有 device:runtime:* key 的数量
        online_count = await redis.eval(
            "return #redis.call('keys', ARGV[1])",
            0,
            "device:runtime:*",
        )
        result.total_devices_online = int(online_count or 0)
    except Exception:
        pass

    return result
