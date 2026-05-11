r"""
文件位置: app/routers/agent_scope_management.py
文件名称: agent_scope_management.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-08
版本: V1.0.0
功能说明:
    代理端对子代理的范围管理能力。

接口前缀:
    /api/agents/scope

设计边界:
    - 只允许代理管理自己代理树范围内的下级代理。
    - 不允许代理通过 scope 接口修改自己。
    - 不允许代理越权管理非自己子树代理。
    - 业务画像、项目授权、点数管理、修改密码都走 scope 专用接口。
    - 管理员端仍使用 admin 专用接口。

注意:
    本文件不替代 app/routers/agents.py。
    agents.py 仍保留:
      - /auth/login
      - /me
      - /my-projects
      - /scope/list
      - /scope
      - /scope/{agent_id}
      - /scope/{agent_id}/subtree
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_agent
from app.core.security import hash_password
from app.core.utils import get_agent_scope_ids
from app.database import get_main_db
from app.models.main.accounting import AccountingWallet
from app.models.main.agent_profile import AgentBusinessProfile
from app.models.main.models import Agent, AgentProjectAuth, GameProject
from app.models.main.project_access import AgentLevelPolicy
from app.services.accounting_service import (
    _append_ledger_entry,
    _create_document,
    get_agent_balance,
    get_balance_transactions,
    get_or_create_wallet,
)
from app.services.audit_service import create_audit_log

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# 请求模型
# ─────────────────────────────────────────────────────────────

class ScopeBusinessProfileUpdate(BaseModel):
    tier_level: int | None = Field(default=None, ge=1, le=4)
    risk_status: str | None = Field(default=None)
    remark: str | None = Field(default=None)

    credit_limit_override: float | None = Field(default=None, ge=0)
    max_credit_limit_override: float | None = Field(default=None, ge=0)
    can_create_sub_agents_override: bool | None = Field(default=None)
    max_sub_agents_override: int | None = Field(default=None, ge=0)


class ScopeProjectAuthCreate(BaseModel):
    project_id: int
    valid_until: datetime | None = None
    granted_reason: str | None = None


class ScopeProjectAuthUpdate(BaseModel):
    valid_until: datetime | None = None
    status: str | None = Field(default=None)


class ScopeAmountRequest(BaseModel):
    amount: float = Field(..., gt=0)
    description: str | None = None


class ScopePasswordResetRequest(BaseModel):
    auto_generate: bool = True
    new_password: str | None = None


# ─────────────────────────────────────────────────────────────
# 基础工具
# ─────────────────────────────────────────────────────────────

def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _as_float(value) -> float:
    return float(value or 0)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _target_agent_or_404(
    *,
    db: AsyncSession,
    current_agent: Agent,
    target_agent_id: int,
    allow_self: bool = False,
) -> Agent:
    if not allow_self and target_agent_id == current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理不能在此入口操作自己的代理账号",
        )

    scope_ids = await get_agent_scope_ids(db, current_agent.id)
    if target_agent_id not in scope_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该代理",
        )

    target = await db.get(Agent, target_agent_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在",
        )

    return target


async def _get_policy(
    *,
    db: AsyncSession,
    level: int,
) -> AgentLevelPolicy | None:
    result = await db.execute(
        select(AgentLevelPolicy).where(
            AgentLevelPolicy.level == level,
            AgentLevelPolicy.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _profile_dict(
    *,
    db: AsyncSession,
    agent_id: int,
    create_if_missing: bool = False,
) -> dict:
    profile_result = await db.execute(
        select(AgentBusinessProfile).where(
            AgentBusinessProfile.agent_id == agent_id
        )
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None and create_if_missing:
        profile = AgentBusinessProfile(
            agent_id=agent_id,
            tier_level=1,
            risk_status="normal",
        )
        db.add(profile)
        await db.flush()
        await db.refresh(profile)

    if profile is None:
        policy = await _get_policy(db=db, level=1)
        return {
            "agent_id": agent_id,
            "tier_level": 1,
            "tier_name": policy.level_name if policy else "Lv.1 新手代理",
            "risk_status": "normal",
            "remark": None,
            "credit_limit": _as_float(policy.default_credit_limit if policy else 0),
            "max_credit_limit": _as_float(policy.max_credit_limit if policy else 0),
            "credit_limit_override": None,
            "max_credit_limit_override": None,
            "can_create_sub_agents": bool(policy.can_create_sub_agents if policy else False),
            "max_sub_agents": int(policy.max_sub_agents if policy else 0),
            "can_create_sub_agents_override": None,
            "max_sub_agents_override": None,
        }

    policy = await _get_policy(db=db, level=profile.tier_level)

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
        "tier_name": policy.level_name if policy else f"Lv.{profile.tier_level}",
        "risk_status": profile.risk_status,
        "remark": profile.remark,
        "credit_limit": credit_limit,
        "max_credit_limit": max_credit_limit,
        "credit_limit_override": (
            _as_float(profile.credit_limit_override)
            if profile.credit_limit_override is not None
            else None
        ),
        "max_credit_limit_override": (
            _as_float(profile.max_credit_limit_override)
            if profile.max_credit_limit_override is not None
            else None
        ),
        "can_create_sub_agents": can_create_sub_agents,
        "max_sub_agents": max_sub_agents,
        "can_create_sub_agents_override": profile.can_create_sub_agents_override,
        "max_sub_agents_override": profile.max_sub_agents_override,
    }


async def _current_agent_profile(
    *,
    db: AsyncSession,
    current_agent: Agent,
) -> dict:
    return await _profile_dict(
        db=db,
        agent_id=current_agent.id,
        create_if_missing=True,
    )

def _allowed_child_tier_level(parent_tier_level: int) -> int | None:
    """
    当前代理允许创建 / 设置的直属下级业务等级。

    当前规则:
      - 只允许比自身业务等级低一级。
      - Lv.4 -> Lv.3
      - Lv.3 -> Lv.2
      - Lv.2 -> Lv.1
      - Lv.1 -> 不允许继续创建下级业务等级
    """
    parent_level = int(parent_tier_level or 0)
    if parent_level <= 1:
        return None
    return parent_level - 1


async def _assert_scope_tier_level_allowed(
    *,
    db: AsyncSession,
    current_agent: Agent,
    requested_tier_level: int,
) -> None:
    """
    校验代理端是否允许给下级设置指定业务等级。

    注意:
      - 管理员端不走这里。
      - 代理端必须严格低一级。
    """
    current_profile = await _current_agent_profile(
        db=db,
        current_agent=current_agent,
    )

    allowed_level = _allowed_child_tier_level(
        int(current_profile["tier_level"])
    )

    if allowed_level is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前代理业务等级不允许创建或设置下级代理业务等级",
        )

    if int(requested_tier_level) != int(allowed_level):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"代理只能设置比自身低一级的业务等级，当前只允许设置 Lv.{allowed_level}",
        )

async def _project_auth_rows(
    *,
    db: AsyncSession,
    agent_id: int,
) -> list[dict]:
    result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id == agent_id)
        .order_by(GameProject.display_name)
    )

    rows = []
    now = _now()

    for auth, project in result.all():
        valid_until = _aware(auth.valid_until)
        rows.append(
            {
                "id": auth.id,
                "agent_id": auth.agent_id,
                "project_id": auth.project_id,
                "project_display_name": project.display_name,
                "display_name": project.display_name,
                "project_code": project.code_name,
                "game_project_code": project.code_name,
                "project_type": project.project_type,
                "valid_until": valid_until,
                "status": auth.status,
                "source": auth.source,
                "granted_at": auth.granted_at,
                "granted_reason": auth.granted_reason,
                "is_expired": valid_until is not None and valid_until <= now,
            }
        )

    return rows


async def _active_project_auth(
    *,
    db: AsyncSession,
    agent_id: int,
    project_id: int,
) -> AgentProjectAuth | None:
    result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.project_id == project_id,
            AgentProjectAuth.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def _ensure_parent_project_scope(
    *,
    db: AsyncSession,
    current_agent: Agent,
    project_id: int,
    child_valid_until: datetime | None,
) -> AgentProjectAuth:
    parent_auth = await _active_project_auth(
        db=db,
        agent_id=current_agent.id,
        project_id=project_id,
    )

    if parent_auth is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前代理未授权该项目，不能给下级开通",
        )

    parent_until = _aware(parent_auth.valid_until)
    child_until = _aware(child_valid_until)

    if parent_until is not None and parent_until <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前代理的项目授权已过期，不能给下级开通",
        )

    if parent_until is not None:
        if child_until is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="父级项目授权有到期时间，下级不能设置为永久",
            )

        if child_until > parent_until:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="下级项目到期时间不能晚于父级项目到期时间",
            )

    return parent_auth


async def _ensure_wallet_can_out(
    *,
    wallet: AccountingWallet,
    amount: Decimal,
    balance_type: str,
) -> Decimal:
    if balance_type == "charged":
        before = _money(wallet.charged_balance)
    elif balance_type == "credit":
        before = _money(wallet.credit_balance) - _money(wallet.frozen_credit)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="余额类型错误",
        )

    if before < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上级代理可用点数不足",
        )

    return before


async def _transfer_points(
    *,
    db: AsyncSession,
    from_agent_id: int,
    to_agent_id: int,
    amount: float,
    balance_type: str,
    entry_type: str,
    description: str | None,
    operator_agent_id: int,
) -> dict:
    """
    代理向直属/下级代理划拨点数。

    recharge:
      - charged -> charged
    credit:
      - credit -> credit

    注意:
      - 代理端不会凭空给下级加点，必须从上级钱包扣减。
      - 管理员端充值/授信仍走 admin accounting 接口。
    """
    amount_dec = _money(amount)
    if amount_dec <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="金额必须大于 0",
        )

    from_wallet = await get_or_create_wallet(from_agent_id, db, for_update=True)
    to_wallet = await get_or_create_wallet(to_agent_id, db, for_update=True)

    from_available_before = await _ensure_wallet_can_out(
        wallet=from_wallet,
        amount=amount_dec,
        balance_type=balance_type,
    )

    document = await _create_document(
        document_type=entry_type,
        agent_id=to_agent_id,
        db=db,
        total_amount=amount_dec,
        reason=description,
        created_by_agent_id=operator_agent_id,
    )

    if balance_type == "charged":
        from_before = _money(from_wallet.charged_balance)
        from_after = from_before - amount_dec
        to_before = _money(to_wallet.charged_balance)
        to_after = to_before + amount_dec

        from_wallet.charged_balance = from_after
        to_wallet.charged_balance = to_after
        to_wallet.total_recharged = _money(to_wallet.total_recharged) + amount_dec
        to_wallet.last_recharge_at = _now()
    else:
        from_before = _money(from_wallet.credit_balance)
        from_after = from_before - amount_dec
        to_before = _money(to_wallet.credit_balance)
        to_after = to_before + amount_dec

        from_wallet.credit_balance = from_after
        to_wallet.credit_balance = to_after
        to_wallet.total_credited = _money(to_wallet.total_credited) + amount_dec
        to_wallet.last_credit_at = _now()

    text = description or f"代理范围内划拨 {amount_dec} 点"

    await _append_ledger_entry(
        db=db,
        wallet=from_wallet,
        document=document,
        direction="out",
        entry_type=entry_type,
        balance_type=balance_type,
        amount=amount_dec,
        balance_before=from_before,
        balance_after=from_after,
        business_category="agent_scope_transfer",
        business_subtype=f"{entry_type}_out",
        description=f"划拨给下级代理 {to_agent_id}：{text}",
        business_text=f"划拨给下级代理 {to_agent_id}：{text}",
        source="agent",
        operated_by_agent_id=operator_agent_id,
    )

    await _append_ledger_entry(
        db=db,
        wallet=to_wallet,
        document=document,
        direction="in",
        entry_type=entry_type,
        balance_type=balance_type,
        amount=amount_dec,
        balance_before=to_before,
        balance_after=to_after,
        business_category="agent_scope_transfer",
        business_subtype=f"{entry_type}_in",
        description=f"上级代理 {from_agent_id} 划拨：{text}",
        business_text=f"上级代理 {from_agent_id} 划拨：{text}",
        source="agent",
        operated_by_agent_id=operator_agent_id,
    )

    await db.flush()
    return await get_agent_balance(to_agent_id, db)


# ─────────────────────────────────────────────────────────────
# 等级策略
# ─────────────────────────────────────────────────────────────

@router.get("/level-policies", summary="代理端获取可设置的下级业务等级策略")
async def scope_level_policies(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    """
    代理端获取自己允许设置给下级代理的业务等级策略。

    当前规则:
      - 只返回比当前代理低一级的业务等级。
      - 不返回等于或高于自身等级的等级。
    """
    current_profile = await _current_agent_profile(
        db=db,
        current_agent=current_agent,
    )

    allowed_level = _allowed_child_tier_level(
        int(current_profile["tier_level"])
    )

    if allowed_level is None:
        return []

    result = await db.execute(
        select(AgentLevelPolicy)
        .where(
            AgentLevelPolicy.is_active == True,  # noqa: E712
            AgentLevelPolicy.level == allowed_level,
        )
        .order_by(AgentLevelPolicy.level)
    )

    rows = result.scalars().all()

    return [
        {
            "id": item.id,
            "level": item.level,
            "level_name": item.level_name,
            "description": item.description,
            "default_credit_limit": _as_float(item.default_credit_limit),
            "max_credit_limit": _as_float(item.max_credit_limit),
            "can_create_sub_agents": item.can_create_sub_agents,
            "max_sub_agents": item.max_sub_agents,
            "can_auto_open_project": item.can_auto_open_project,
            "auto_open_project_limit": item.auto_open_project_limit,
            "review_priority": item.review_priority,
            "is_active": item.is_active,
        }
        for item in rows
    ]


# ─────────────────────────────────────────────────────────────
# 业务画像
# ─────────────────────────────────────────────────────────────

@router.get("/{agent_id}/business-profile", summary="代理端查看下级业务画像")
async def scope_get_business_profile(
    agent_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await _profile_dict(
        db=db,
        agent_id=agent_id,
        create_if_missing=True,
    )


@router.patch("/{agent_id}/business-profile", summary="代理端更新下级业务画像")
async def scope_update_business_profile(
    agent_id: int,
    body: ScopeBusinessProfileUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    current_profile = await _current_agent_profile(
        db=db,
        current_agent=current_agent,
    )

    profile_result = await db.execute(
        select(AgentBusinessProfile).where(AgentBusinessProfile.agent_id == target.id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        profile = AgentBusinessProfile(
            agent_id=target.id,
            tier_level=1,
            risk_status="normal",
        )
        db.add(profile)
        await db.flush()

    if body.tier_level is not None:
        await _assert_scope_tier_level_allowed(
            db=db,
            current_agent=current_agent,
            requested_tier_level=body.tier_level,
        )
        profile.tier_level = body.tier_level

    if body.risk_status is not None:
        if body.risk_status not in {"normal", "watch", "restricted", "frozen"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="风险状态非法",
            )
        profile.risk_status = body.risk_status

    if body.remark is not None:
        profile.remark = body.remark

    policy = await _get_policy(db=db, level=profile.tier_level)

    if body.credit_limit_override is not None:
        if policy and body.credit_limit_override > _as_float(policy.max_credit_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="默认授信覆盖不能高于该等级最高授信",
            )
        profile.credit_limit_override = body.credit_limit_override

    if body.max_credit_limit_override is not None:
        if policy and body.max_credit_limit_override > _as_float(policy.max_credit_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="最高授信覆盖不能高于该等级最高授信",
            )
        profile.max_credit_limit_override = body.max_credit_limit_override

    if body.can_create_sub_agents_override is not None:
        profile.can_create_sub_agents_override = body.can_create_sub_agents_override

    if body.max_sub_agents_override is not None:
        profile.max_sub_agents_override = body.max_sub_agents_override

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.business_profile.update",
        target_type="agent",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 更新下级代理 {target.username} 业务画像",
        metadata=body.model_dump(exclude_unset=True),
    )

    await db.flush()
    return await _profile_dict(
        db=db,
        agent_id=target.id,
        create_if_missing=True,
    )


# ─────────────────────────────────────────────────────────────
# 项目授权
# ─────────────────────────────────────────────────────────────

@router.get("/{agent_id}/project-auths", summary="代理端查看下级项目授权")
async def scope_list_project_auths(
    agent_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await _project_auth_rows(db=db, agent_id=target.id)


@router.post("/{agent_id}/project-auths", summary="代理端给下级开通项目")
async def scope_grant_project_auth(
    agent_id: int,
    body: ScopeProjectAuthCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    await _ensure_parent_project_scope(
        db=db,
        current_agent=current_agent,
        project_id=body.project_id,
        child_valid_until=body.valid_until,
    )

    project = await db.get(GameProject, body.project_id)
    if project is None or not project.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在或已停用",
        )

    existing_result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == target.id,
            AgentProjectAuth.project_id == body.project_id,
        )
    )
    auth = existing_result.scalar_one_or_none()

    if auth is None:
        auth = AgentProjectAuth(
            agent_id=target.id,
            project_id=body.project_id,
            valid_until=body.valid_until,
            status="active",
            source="auto_approved",
            granted_reason=body.granted_reason or f"上级代理 {current_agent.username} 开通",
        )
        db.add(auth)
    else:
        auth.valid_until = body.valid_until
        auth.status = "active"
        auth.source = auth.source or "auto_approved"
        auth.granted_reason = body.granted_reason or f"上级代理 {current_agent.username} 重新开通"

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.project_auth.grant",
        target_type="agent_project_auth",
        target_id=auth.id,
        summary=f"代理 {current_agent.username} 给下级代理 {target.username} 开通项目 {project.display_name}",
        metadata={
            "target_agent_id": target.id,
            "project_id": project.id,
            "valid_until": str(body.valid_until) if body.valid_until else None,
        },
    )

    await db.flush()
    return await _project_auth_rows(db=db, agent_id=target.id)


@router.patch("/{agent_id}/project-auths/{auth_id}", summary="代理端更新下级项目授权")
async def scope_update_project_auth(
    agent_id: int,
    auth_id: int,
    body: ScopeProjectAuthUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    auth = await db.get(AgentProjectAuth, auth_id)
    if auth is None or auth.agent_id != target.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目授权不存在",
        )

    if body.valid_until is not None:
        await _ensure_parent_project_scope(
            db=db,
            current_agent=current_agent,
            project_id=auth.project_id,
            child_valid_until=body.valid_until,
        )
        auth.valid_until = body.valid_until

    if body.status is not None:
        if body.status not in {"active", "suspended"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目授权状态非法",
            )
        auth.status = body.status

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.project_auth.update",
        target_type="agent_project_auth",
        target_id=auth.id,
        summary=f"代理 {current_agent.username} 更新下级代理 {target.username} 项目授权",
        metadata=body.model_dump(exclude_unset=True),
    )

    await db.flush()
    return await _project_auth_rows(db=db, agent_id=target.id)


@router.delete("/{agent_id}/project-auths/{auth_id}", summary="代理端停用下级项目授权")
async def scope_revoke_project_auth(
    agent_id: int,
    auth_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    auth = await db.get(AgentProjectAuth, auth_id)
    if auth is None or auth.agent_id != target.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目授权不存在",
        )

    auth.status = "suspended"

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.project_auth.revoke",
        target_type="agent_project_auth",
        target_id=auth.id,
        summary=f"代理 {current_agent.username} 停用下级代理 {target.username} 项目授权",
        metadata={
            "target_agent_id": target.id,
            "project_id": auth.project_id,
        },
    )

    await db.flush()
    return await _project_auth_rows(db=db, agent_id=target.id)


# ─────────────────────────────────────────────────────────────
# 点数管理
# ─────────────────────────────────────────────────────────────

@router.get("/{agent_id}/balance", summary="代理端查看下级余额")
async def scope_get_balance(
    agent_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await get_agent_balance(target.id, db)


@router.get("/{agent_id}/transactions", summary="代理端查看下级流水")
async def scope_get_transactions(
    agent_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    entry_type: str | None = Query(default=None),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )
    return await get_balance_transactions(
        agent_id=target.id,
        db=db,
        page=page,
        page_size=page_size,
        entry_type=entry_type,
    )


@router.post("/{agent_id}/recharge", summary="代理端给下级划拨充值点数")
async def scope_recharge(
    agent_id: int,
    body: ScopeAmountRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    result = await _transfer_points(
        db=db,
        from_agent_id=current_agent.id,
        to_agent_id=target.id,
        amount=body.amount,
        balance_type="charged",
        entry_type="recharge",
        description=body.description,
        operator_agent_id=current_agent.id,
    )

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.accounting.recharge",
        target_type="accounting_wallet",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 给下级代理 {target.username} 划拨充值点数 {body.amount}",
        metadata=body.model_dump(),
    )

    return result


@router.post("/{agent_id}/credit", summary="代理端给下级划拨授信点数")
async def scope_credit(
    agent_id: int,
    body: ScopeAmountRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    profile = await _profile_dict(
        db=db,
        agent_id=target.id,
        create_if_missing=True,
    )
    max_credit = _money(profile["max_credit_limit"])
    current_balance = await get_agent_balance(target.id, db)
    target_credit_after = _money(current_balance.get("credit_balance")) + _money(body.amount)

    if max_credit > 0 and target_credit_after > max_credit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"授信后将超过该业务等级最高授信 {max_credit}",
        )

    result = await _transfer_points(
        db=db,
        from_agent_id=current_agent.id,
        to_agent_id=target.id,
        amount=body.amount,
        balance_type="credit",
        entry_type="credit",
        description=body.description,
        operator_agent_id=current_agent.id,
    )

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.accounting.credit",
        target_type="accounting_wallet",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 给下级代理 {target.username} 划拨授信点数 {body.amount}",
        metadata={
            **body.model_dump(),
            "target_profile": profile,
        },
    )

    return result


@router.post("/{agent_id}/freeze", summary="代理端冻结下级授信")
async def scope_freeze(
    agent_id: int,
    body: ScopeAmountRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    amount = _money(body.amount)
    wallet = await get_or_create_wallet(target.id, db, for_update=True)

    available_credit = _money(wallet.credit_balance) - _money(wallet.frozen_credit)
    if available_credit < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="下级代理可冻结授信不足",
        )

    document = await _create_document(
        document_type="freeze",
        agent_id=target.id,
        db=db,
        total_amount=amount,
        reason=body.description,
        created_by_agent_id=current_agent.id,
    )

    before = _money(wallet.frozen_credit)
    after = before + amount
    wallet.frozen_credit = after

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="out",
        entry_type="freeze",
        balance_type="credit",
        amount=amount,
        balance_before=before,
        balance_after=after,
        business_category="agent_scope_accounting",
        business_subtype="freeze",
        description=body.description or "上级代理冻结授信",
        source="agent",
        operated_by_agent_id=current_agent.id,
    )

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.accounting.freeze",
        target_type="accounting_wallet",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 冻结下级代理 {target.username} 授信 {body.amount}",
        metadata=body.model_dump(),
    )

    await db.flush()
    return await get_agent_balance(target.id, db)


@router.post("/{agent_id}/unfreeze", summary="代理端解冻下级授信")
async def scope_unfreeze(
    agent_id: int,
    body: ScopeAmountRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    amount = _money(body.amount)
    wallet = await get_or_create_wallet(target.id, db, for_update=True)

    before = _money(wallet.frozen_credit)
    if before < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="解冻金额不能大于已冻结授信",
        )

    after = before - amount
    wallet.frozen_credit = after

    document = await _create_document(
        document_type="unfreeze",
        agent_id=target.id,
        db=db,
        total_amount=amount,
        reason=body.description,
        created_by_agent_id=current_agent.id,
    )

    await _append_ledger_entry(
        db=db,
        wallet=wallet,
        document=document,
        direction="in",
        entry_type="unfreeze",
        balance_type="credit",
        amount=amount,
        balance_before=before,
        balance_after=after,
        business_category="agent_scope_accounting",
        business_subtype="unfreeze",
        description=body.description or "上级代理解冻授信",
        source="agent",
        operated_by_agent_id=current_agent.id,
    )

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.accounting.unfreeze",
        target_type="accounting_wallet",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 解冻下级代理 {target.username} 授信 {body.amount}",
        metadata=body.model_dump(),
    )

    await db.flush()
    return await get_agent_balance(target.id, db)


# ─────────────────────────────────────────────────────────────
# 修改密码
# ─────────────────────────────────────────────────────────────

@router.post("/{agent_id}/password", summary="代理端重置下级代理密码")
async def scope_reset_password(
    agent_id: int,
    body: ScopePasswordResetRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    target = await _target_agent_or_404(
        db=db,
        current_agent=current_agent,
        target_agent_id=agent_id,
    )

    if body.auto_generate:
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        new_password = "".join(secrets.choice(alphabet) for _ in range(12))
    else:
        if not body.new_password or len(body.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码至少 6 位",
            )
        new_password = body.new_password

    target.password_hash = hash_password(new_password)

    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="agent.scope.password.reset",
        target_type="agent",
        target_id=target.id,
        summary=f"代理 {current_agent.username} 重置下级代理 {target.username} 密码",
        metadata={
            "target_agent_id": target.id,
            "auto_generate": body.auto_generate,
        },
    )

    await db.flush()

    return {
        "ok": True,
        "agent_id": target.id,
        "generated_password": new_password if body.auto_generate else None,
    }