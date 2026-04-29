r"""
文件位置: app/routers/agent_profile_admin.py
文件名称: agent_profile_admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    管理员端代理业务等级、业务画像、密码重置接口。

挂载建议:
    app.include_router(agent_profile_admin.router, prefix="/admin/api", tags=["代理业务管理"])
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.schemas.agent_profile import (
    AgentBusinessProfileResponse,
    AgentBusinessProfileUpdateRequest,
    AgentLevelPolicyAdminResponse,
    AgentLevelPolicyUpdateRequest,
    AgentPasswordResetRequest,
    AgentPasswordResetResponse,
)
from app.services.agent_profile_service import (
    get_agent_business_profile,
    list_agent_level_policies,
    reset_agent_password,
    update_agent_business_profile,
    update_agent_level_policy,
)

router = APIRouter()


@router.get(
    "/agent-level-policies",
    response_model=list[AgentLevelPolicyAdminResponse],
    summary="代理等级策略列表",
)
async def agent_level_policies(
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> list[AgentLevelPolicyAdminResponse]:
    return await list_agent_level_policies(db=db)


@router.patch(
    "/agent-level-policies/{level}",
    response_model=AgentLevelPolicyAdminResponse,
    summary="更新代理等级策略",
)
async def update_level_policy(
    level: int,
    body: AgentLevelPolicyUpdateRequest,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentLevelPolicyAdminResponse:
    return await update_agent_level_policy(
        level=level,
        body=body,
        db=db,
    )


@router.get(
    "/agents/{agent_id}/business-profile",
    response_model=AgentBusinessProfileResponse,
    summary="查询代理业务画像",
)
async def agent_business_profile(
    agent_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentBusinessProfileResponse:
    return await get_agent_business_profile(
        agent_id=agent_id,
        db=db,
    )


@router.patch(
    "/agents/{agent_id}/business-profile",
    response_model=AgentBusinessProfileResponse,
    summary="更新代理业务画像",
)
async def update_business_profile(
    agent_id: int,
    body: AgentBusinessProfileUpdateRequest,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentBusinessProfileResponse:
    return await update_agent_business_profile(
        agent_id=agent_id,
        body=body,
        db=db,
    )


@router.post(
    "/agents/{agent_id}/password",
    response_model=AgentPasswordResetResponse,
    summary="管理员重置代理密码",
)
async def reset_password(
    agent_id: int,
    body: AgentPasswordResetRequest,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentPasswordResetResponse:
    return await reset_agent_password(
        agent_id=agent_id,
        body=body,
        db=db,
    )