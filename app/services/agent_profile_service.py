r"""
文件位置: app/services/agent_profile_service.py
文件名称: agent_profile_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    管理员端代理业务等级、业务画像、密码重置服务。

边界:
    - 不修改 Agent.level 的含义。
    - Agent.level 继续表示组织层级 / 代理树深度。
    - AgentBusinessProfile.tier_level 表示代理业务等级。
    - AgentLevelPolicy 只表达授信、下级代理、自动开通和审核优先级。
    - 用户数量只作为统计展示。
"""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.utils import generate_password as _generate_password, now_utc as _now
from app.models.main.models import Agent
from app.models.main.agent_profile import AgentBusinessProfile
from app.models.main.project_access import AgentLevelPolicy
from app.schemas.agent_profile import (
    AgentBusinessProfileResponse,
    AgentBusinessProfileUpdateRequest,
    AgentLevelPolicyAdminResponse,
    AgentLevelPolicyUpdateRequest,
    AgentPasswordResetRequest,
    AgentPasswordResetResponse,
)


def _as_float(value) -> float:
    return float(value or 0)


async def list_agent_level_policies(
    *,
    db: AsyncSession,
) -> list[AgentLevelPolicyAdminResponse]:
    result = await db.execute(
        select(AgentLevelPolicy).order_by(AgentLevelPolicy.level.asc())
    )
    policies = result.scalars().all()
    return [_policy_to_response(policy) for policy in policies]


async def update_agent_level_policy(
    *,
    level: int,
    body: AgentLevelPolicyUpdateRequest,
    db: AsyncSession,
) -> AgentLevelPolicyAdminResponse:
    if level < 1 or level > 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理等级必须在 Lv.1 - Lv.4 之间")

    result = await db.execute(
        select(AgentLevelPolicy).where(AgentLevelPolicy.level == level)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理等级策略不存在")

    data = body.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(policy, key, value)

    if policy.max_credit_limit < policy.default_credit_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最高授信额度不能低于默认授信额度",
        )

    policy.updated_at = _now()

    await db.flush()
    await db.refresh(policy)

    return _policy_to_response(policy)


async def get_agent_business_profile(
    *,
    agent_id: int,
    db: AsyncSession,
) -> AgentBusinessProfileResponse:
    agent = await _get_agent_or_404(agent_id, db)
    profile = await _get_or_create_profile(agent.id, db)
    policy = await _get_level_policy_or_404(profile.tier_level, db)

    return _profile_to_response(agent, profile, policy)


async def update_agent_business_profile(
    *,
    agent_id: int,
    body: AgentBusinessProfileUpdateRequest,
    db: AsyncSession,
) -> AgentBusinessProfileResponse:
    agent = await _get_agent_or_404(agent_id, db)
    profile = await _get_or_create_profile(agent.id, db)

    data = body.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(profile, key, value)

    if profile.tier_level < 1 or profile.tier_level > 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理业务等级必须在 Lv.1 - Lv.4 之间")

    if (
        profile.credit_limit_override is not None
        and profile.max_credit_limit_override is not None
        and profile.max_credit_limit_override < profile.credit_limit_override
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="代理最高授信覆盖值不能低于默认授信覆盖值",
        )

    policy = await _get_level_policy_or_404(profile.tier_level, db)

    profile.updated_at = _now()

    await db.flush()
    await db.refresh(profile)

    return _profile_to_response(agent, profile, policy)


async def reset_agent_password(
    *,
    agent_id: int,
    body: AgentPasswordResetRequest,
    db: AsyncSession,
) -> AgentPasswordResetResponse:
    agent = await _get_agent_or_404(agent_id, db)

    if body.auto_generate:
        new_password = _generate_password()
    else:
        if not body.new_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手动重置密码时必须提供新密码")
        new_password = body.new_password

    agent.password_hash = hash_password(new_password)
    agent.updated_at = _now()

    await db.flush()

    return AgentPasswordResetResponse(
        agent_id=agent.id,
        username=agent.username,
        generated_password=new_password if body.auto_generate else None,
    )


async def get_agent_effective_tier_level(
    *,
    agent_id: int,
    db: AsyncSession,
) -> int:
    """
    给其他服务调用的统一入口。

    用途:
        项目准入策略不要再读 Agent.level。
        后续应该统一读取这里返回的业务等级。
    """
    profile = await _get_or_create_profile(agent_id, db)
    return profile.tier_level


async def _get_agent_or_404(agent_id: int, db: AsyncSession) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在")

    return agent


async def _get_or_create_profile(
    agent_id: int,
    db: AsyncSession,
) -> AgentBusinessProfile:
    result = await db.execute(
        select(AgentBusinessProfile).where(AgentBusinessProfile.agent_id == agent_id)
    )
    profile = result.scalar_one_or_none()

    if profile:
        return profile

    profile = AgentBusinessProfile(
        agent_id=agent_id,
        tier_level=1,
        risk_status="normal",
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    return profile


async def _ensure_level_policies(db: AsyncSession) -> None:
    """自动创建默认等级策略（Lv.1 - Lv.4），幂等。"""
    defaults: list[dict] = [
        {"level": 1, "level_name": "Lv.1 初级代理", "default_credit_limit": 100.0, "max_credit_limit": 500.0,
         "can_create_sub_agents": False, "max_sub_agents": 0, "can_auto_open_project": False,
         "auto_open_project_limit": 0, "review_priority": 0, "is_active": True},
        {"level": 2, "level_name": "Lv.2 中级代理", "default_credit_limit": 500.0, "max_credit_limit": 2000.0,
         "can_create_sub_agents": True, "max_sub_agents": 5, "can_auto_open_project": False,
         "auto_open_project_limit": 0, "review_priority": 1, "is_active": True},
        {"level": 3, "level_name": "Lv.3 高级代理", "default_credit_limit": 2000.0, "max_credit_limit": 10000.0,
         "can_create_sub_agents": True, "max_sub_agents": 20, "can_auto_open_project": True,
         "auto_open_project_limit": 3, "review_priority": 2, "is_active": True},
        {"level": 4, "level_name": "Lv.4 顶级代理", "default_credit_limit": 10000.0, "max_credit_limit": 50000.0,
         "can_create_sub_agents": True, "max_sub_agents": 100, "can_auto_open_project": True,
         "auto_open_project_limit": 10, "review_priority": 3, "is_active": True},
    ]
    for d in defaults:
        result = await db.execute(
            select(AgentLevelPolicy).where(AgentLevelPolicy.level == d["level"])
        )
        if not result.scalar_one_or_none():
            db.add(AgentLevelPolicy(**d))
    await db.flush()


async def _get_level_policy_or_404(
    level: int,
    db: AsyncSession,
) -> AgentLevelPolicy:
    await _ensure_level_policies(db)
    result = await db.execute(
        select(AgentLevelPolicy).where(AgentLevelPolicy.level == level)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"代理等级策略 Lv.{level} 不存在")

    return policy


def _policy_to_response(policy: AgentLevelPolicy) -> AgentLevelPolicyAdminResponse:
    return AgentLevelPolicyAdminResponse(
        id=policy.id,
        level=policy.level,
        level_name=policy.level_name,
        description=policy.description,
        default_credit_limit=_as_float(policy.default_credit_limit),
        max_credit_limit=_as_float(policy.max_credit_limit),
        can_create_sub_agents=policy.can_create_sub_agents,
        max_sub_agents=policy.max_sub_agents,
        can_auto_open_project=policy.can_auto_open_project,
        auto_open_project_limit=policy.auto_open_project_limit,
        review_priority=policy.review_priority,
        is_active=policy.is_active,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _profile_to_response(
    agent: Agent,
    profile: AgentBusinessProfile,
    policy: AgentLevelPolicy,
) -> AgentBusinessProfileResponse:
    credit_limit = (
        _as_float(profile.credit_limit_override)
        if profile.credit_limit_override is not None
        else _as_float(policy.default_credit_limit)
    )

    max_credit_limit = (
        _as_float(profile.max_credit_limit_override)
        if profile.max_credit_limit_override is not None
        else _as_float(policy.max_credit_limit)
    )

    can_create_sub_agents = (
        profile.can_create_sub_agents_override
        if profile.can_create_sub_agents_override is not None
        else policy.can_create_sub_agents
    )

    max_sub_agents = (
        profile.max_sub_agents_override
        if profile.max_sub_agents_override is not None
        else policy.max_sub_agents
    )

    return AgentBusinessProfileResponse(
        agent_id=agent.id,
        username=agent.username,
        hierarchy_level=agent.hierarchy_depth,
        tier_level=profile.tier_level,
        tier_name=policy.level_name,
        risk_status=profile.risk_status,
        remark=profile.remark,

        credit_limit=credit_limit,
        max_credit_limit=max_credit_limit,
        credit_limit_override=_as_float(profile.credit_limit_override)
        if profile.credit_limit_override is not None else None,
        max_credit_limit_override=_as_float(profile.max_credit_limit_override)
        if profile.max_credit_limit_override is not None else None,

        can_create_sub_agents=bool(can_create_sub_agents),
        max_sub_agents=int(max_sub_agents or 0),
        can_create_sub_agents_override=profile.can_create_sub_agents_override,
        max_sub_agents_override=profile.max_sub_agents_override,

        can_auto_open_project=policy.can_auto_open_project,
        auto_open_project_limit=policy.auto_open_project_limit,

        level_policy=_policy_to_response(policy),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )