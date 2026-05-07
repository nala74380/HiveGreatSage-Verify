r"""
文件位置: app/routers/agent_profile_admin.py
文件名称: agent_profile_admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-07
版本: V1.1.0
功能说明:
    管理员端代理业务等级、业务画像、密码重置接口。

挂载建议:
    app.include_router(agent_profile_admin.router, prefix="/admin/api", tags=["代理业务管理"])

改进历史:
    V1.1.0 (2026-05-07): 等级策略更新、业务画像更新、代理密码重置接入 audit_log。
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
from app.services.audit_service import create_audit_log

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
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentLevelPolicyAdminResponse:
    result = await update_agent_level_policy(
        level=level,
        body=body,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent_level_policy.update",
        target_type="agent_level_policy",
        target_id=result.id,
        summary=f"更新代理等级策略 Lv.{level}",
        metadata={
            "level": level,
            "policy_id": result.id,
            "level_name": result.level_name,
            "changed_fields": body.model_dump(exclude_unset=True),
            "is_active": result.is_active,
        },
    )
    return result


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
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentBusinessProfileResponse:
    result = await update_agent_business_profile(
        agent_id=agent_id,
        body=body,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent_business_profile.update",
        target_type="agent_business_profile",
        target_id=agent_id,
        summary=f"更新代理 {result.username} 业务画像",
        metadata={
            "agent_id": agent_id,
            "username": result.username,
            "changed_fields": body.model_dump(exclude_unset=True),
            "hierarchy_depth": result.hierarchy_depth,
            "tier_level": result.tier_level,
            "tier_name": result.tier_name,
            "risk_status": result.risk_status,
        },
    )
    return result


@router.post(
    "/agents/{agent_id}/password",
    response_model=AgentPasswordResetResponse,
    summary="管理员重置代理密码",
)
async def reset_password(
    agent_id: int,
    body: AgentPasswordResetRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentPasswordResetResponse:
    result = await reset_agent_password(
        agent_id=agent_id,
        body=body,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent.password_reset",
        target_type="agent",
        target_id=agent_id,
        summary=f"重置代理 {result.username} 密码",
        metadata={
            "agent_id": agent_id,
            "username": result.username,
            "auto_generate": body.auto_generate,
        },
    )
    return result
