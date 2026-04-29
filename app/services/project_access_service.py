r"""
文件位置: app/services/project_access_service.py
文件名称: project_access_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.1
功能说明:
    代理等级驱动的项目准入、申请、自动开通、管理员审核服务层。

核心规则:
    - 项目开通本身不扣点。
    - 代理给用户授权项目时才按项目定价扣点。
    - 自动开通也必须写 agent_project_auth_request 审计记录。
    - hidden 项目默认不展示。
    - invite_only 项目只有指定代理可见。

本版修复:
    - 修复管理员批准项目申请时 MissingGreenlet 问题。
    - 原因是 AsyncSession 下访问 expired ORM 字段 req.updated_at 时触发隐式 IO。
    - 处理方式:
        1. 修改状态时手动写入 updated_at。
        2. flush 后显式 await db.refresh(req)。
        3. _request_to_response() 内先快照字段，避免后续 await 后再次访问 expired 字段。
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import (
    Admin,
    Agent,
    AgentBalance,
    AgentProjectAuth,
    GameProject,
    ProjectPrice,
)
from app.models.main.project_access import (
    AgentProjectAccessInvite,
    AgentProjectAuthRequest,
    ProjectAccessPolicy,
)
from app.schemas.project_access import (
    AgentProjectAuthRequestCreate,
    AgentProjectAuthRequestListResponse,
    AgentProjectAuthRequestResponse,
    AgentProjectCatalogItem,
    ApproveProjectAuthRequest,
    ProjectAccessPolicyResponse,
    ProjectAccessPolicyUpdateRequest,
    RejectProjectAuthRequest,
)


LEVEL_NAMES = {
    "trial": "试用",
    "normal": "普通",
    "vip": "VIP",
    "svip": "SVIP",
}

LEVEL_ORDER = ["trial", "normal", "vip", "svip"]

UNIT_LABELS = {
    "trial": "点/周/设备",
    "normal": "点/月/设备",
    "vip": "点/月/设备",
    "svip": "点/月/设备",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """
    统一 datetime 时区。

    PostgreSQL timezone=True 字段有时返回 aware datetime；
    前端传入的时间也可能带 Z；
    为避免 offset-naive / offset-aware 比较异常，统一兜底。
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt


def _is_future(dt: datetime | None, now: datetime) -> bool:
    """
    判断时间是否未过期。
    None 表示永久有效。
    """
    if dt is None:
        return True

    normalized_dt = _ensure_aware(dt)
    normalized_now = _ensure_aware(now)

    if normalized_dt is None or normalized_now is None:
        return True

    return normalized_dt > normalized_now


def _as_float(value) -> float:
    return float(value or 0)


async def _refresh_request_for_response(
    req: AgentProjectAuthRequest,
    db: AsyncSession,
) -> AgentProjectAuthRequest:
    """
    显式刷新代理项目申请对象，避免 AsyncSession 下访问 expired 字段触发 MissingGreenlet。

    背景:
        SQLAlchemy AsyncSession 中，server_default / onupdate 字段在 flush 后可能被标记为 expired。
        如果之后直接访问 req.updated_at，SQLAlchemy 会尝试隐式 IO。
        隐式 IO 在普通属性访问中不能 await，因此会抛 MissingGreenlet。

    处理:
        在构造响应前显式 refresh，把可能 expired 的字段主动加载回来。
    """
    await db.refresh(req)
    return req


# ═══════════════════════════════════════════════════════════════
# 代理端：项目目录
# ═══════════════════════════════════════════════════════════════

async def list_agent_project_catalog(
    *,
    agent: Agent,
    db: AsyncSession,
) -> list[AgentProjectCatalogItem]:
    """
    代理项目目录。

    返回的是经过项目准入策略过滤后的项目列表。
    """
    now = _now()

    project_result = await db.execute(
        select(GameProject)
        .where(GameProject.is_active == True)  # noqa: E712
        .order_by(GameProject.id.asc())
    )
    projects = project_result.scalars().all()

    if not projects:
        return []

    project_ids = [project.id for project in projects]

    policy_map = await _load_policy_map(project_ids, db)
    price_map = await _load_price_map(project_ids, db)
    authorized_map = await _load_authorized_project_map(agent.id, db, now)
    request_map = await _load_last_request_map(agent.id, db)

    pending_map = {
        project_id: req
        for project_id, req in request_map.items()
        if req.status == "pending"
    }

    invite_project_ids = await _load_invite_project_ids(agent.id, db)
    available_points = await _get_agent_available_points(agent.id, db)

    rows: list[AgentProjectCatalogItem] = []

    for project in projects:
        policy = policy_map.get(project.id) or _default_policy(project.id)
        auth = authorized_map.get(project.id)
        last_request = request_map.get(project.id)
        pending_request = pending_map.get(project.id)

        is_authorized = auth is not None

        is_visible = _is_project_visible(
            agent=agent,
            policy=policy,
            is_authorized=is_authorized,
            is_invited=project.id in invite_project_ids,
        )

        if not is_visible:
            continue

        can_auto_open = False
        can_apply = False

        if not is_authorized and not pending_request:
            can_auto_open = _can_auto_open(
                agent=agent,
                policy=policy,
                available_points=available_points,
            )
            can_apply = _can_apply(agent=agent, policy=policy)

        if is_authorized:
            access_status = "authorized"
            action_type = "none"
        elif pending_request:
            access_status = "pending"
            action_type = "view_request"
        elif can_auto_open:
            access_status = "auto_open_available"
            action_type = "auto_open"
        elif can_apply:
            access_status = "apply_available"
            action_type = "apply"
        elif last_request and last_request.status == "rejected":
            access_status = "rejected"
            action_type = "apply" if _can_apply(agent=agent, policy=policy) else "none"
        else:
            access_status = "unavailable"
            action_type = "none"

        rows.append(
            AgentProjectCatalogItem(
                id=project.id,
                code_name=project.code_name,
                display_name=project.display_name,
                project_type=project.project_type,
                prices=_build_price_items(price_map.get(project.id, {})),
                access_status=access_status,
                action_type=action_type,
                is_authorized=is_authorized,
                is_visible=True,
                visibility_mode=policy.visibility_mode,
                open_mode=policy.open_mode,
                pending_request_id=pending_request.id if pending_request else None,
                last_request_status=last_request.status if last_request else None,
                last_request_id=last_request.id if last_request else None,
                last_review_note=last_request.review_note if last_request else None,
                auth_valid_until=auth.valid_until if auth else None,
            )
        )

    return rows


# ═══════════════════════════════════════════════════════════════
# 代理端：提交 / 查询 / 取消申请
# ═══════════════════════════════════════════════════════════════

async def create_agent_project_auth_request(
    *,
    agent: Agent,
    body: AgentProjectAuthRequestCreate,
    db: AsyncSession,
) -> AgentProjectAuthRequestResponse:
    """
    代理申请项目开通，或满足条件时自动开通。

    - auto_by_level / auto_by_condition 且满足条件：auto_approved + 写入 agent_project_auth。
    - 其他可申请项目：pending。
    """
    now = _now()

    project = await _get_project_or_404(body.project_id, db)
    policy = await _get_or_create_policy(project.id, db)

    existing_auth = await _get_active_agent_project_auth(agent.id, project.id, db, now)
    if existing_auth:
        raise HTTPException(status_code=400, detail="该项目已授权，无需重复申请")

    existing_pending = await _get_pending_request(agent.id, project.id, db)
    if existing_pending:
        raise HTTPException(status_code=409, detail="该项目已有待审核申请，请勿重复提交")

    invite_project_ids = await _load_invite_project_ids(agent.id, db)

    is_invited = project.id in invite_project_ids
    visible = _is_project_visible(
        agent=agent,
        policy=policy,
        is_authorized=False,
        is_invited=is_invited,
    )

    if not visible:
        raise HTTPException(status_code=403, detail="该项目当前不对你的代理账号开放")

    available_points = await _get_agent_available_points(agent.id, db)
    can_auto = _can_auto_open(agent=agent, policy=policy, available_points=available_points)
    can_apply = _can_apply(agent=agent, policy=policy)

    if can_auto:
        req = AgentProjectAuthRequest(
            agent_id=agent.id,
            project_id=project.id,
            request_reason=body.request_reason,
            status="auto_approved",
            reviewed_at=now,
            updated_at=now,
            auto_approve_reason=_build_auto_approve_reason(agent, policy, available_points),
        )

        db.add(req)
        await db.flush()

        await _grant_agent_project_auth(
            agent_id=agent.id,
            project_id=project.id,
            valid_until=None,
            source="auto_approved",
            request_id=req.id,
            admin_id=None,
            reason=req.auto_approve_reason,
            db=db,
        )

        await db.flush()
        await _refresh_request_for_response(req, db)

        return await _request_to_response(req, db)

    if not can_apply:
        raise HTTPException(status_code=403, detail="该项目当前不允许申请")

    if policy.require_request_reason and not (body.request_reason or "").strip():
        raise HTTPException(status_code=400, detail="该项目申请必须填写申请理由")

    req = AgentProjectAuthRequest(
        agent_id=agent.id,
        project_id=project.id,
        request_reason=body.request_reason,
        status="pending",
        updated_at=now,
    )

    db.add(req)
    await db.flush()
    await _refresh_request_for_response(req, db)

    return await _request_to_response(req, db)


async def list_my_project_auth_requests(
    *,
    agent: Agent,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
) -> AgentProjectAuthRequestListResponse:
    query = select(AgentProjectAuthRequest).where(
        AgentProjectAuthRequest.agent_id == agent.id
    )

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    result = await db.execute(
        query.order_by(AgentProjectAuthRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = []

    for req in result.scalars().all():
        rows.append(await _request_to_response(req, db))

    return AgentProjectAuthRequestListResponse(
        requests=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


async def cancel_my_project_auth_request(
    *,
    request_id: int,
    agent: Agent,
    db: AsyncSession,
) -> AgentProjectAuthRequestResponse:
    req = await _get_request_or_404(request_id, db)

    if req.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="无权取消该申请")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审核申请可以取消")

    now = _now()

    req.status = "cancelled"
    req.updated_at = now

    await db.flush()
    await _refresh_request_for_response(req, db)

    return await _request_to_response(req, db)


# ═══════════════════════════════════════════════════════════════
# 管理员端：项目准入策略
# ═══════════════════════════════════════════════════════════════

async def list_project_access_policies(
    *,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    project_result = await db.execute(
        select(GameProject)
        .where(GameProject.is_active == True)  # noqa: E712
        .order_by(GameProject.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    projects = project_result.scalars().all()

    total = (
        await db.execute(
            select(func.count(GameProject.id)).where(
                GameProject.is_active == True  # noqa: E712
            )
        )
    ).scalar_one()

    rows = []

    for project in projects:
        policy = await _get_or_create_policy(project.id, db)
        rows.append(_policy_to_response(policy, project))

    await db.flush()

    return {
        "policies": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_project_access_policy(
    *,
    project_id: int,
    body: ProjectAccessPolicyUpdateRequest,
    db: AsyncSession,
) -> ProjectAccessPolicyResponse:
    project = await _get_project_or_404(project_id, db)
    policy = await _get_or_create_policy(project.id, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)

    _validate_policy(policy)

    policy.updated_at = _now()

    await db.flush()
    await db.refresh(policy)

    return _policy_to_response(policy, project)


# ═══════════════════════════════════════════════════════════════
# 管理员端：申请列表 / 批准 / 拒绝
# ═══════════════════════════════════════════════════════════════

async def list_all_project_auth_requests(
    *,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    status_filter: str | None = None,
    agent_id: int | None = None,
    project_id: int | None = None,
) -> AgentProjectAuthRequestListResponse:
    query = select(AgentProjectAuthRequest)

    if status_filter:
        query = query.where(AgentProjectAuthRequest.status == status_filter)

    if agent_id:
        query = query.where(AgentProjectAuthRequest.agent_id == agent_id)

    if project_id:
        query = query.where(AgentProjectAuthRequest.project_id == project_id)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    result = await db.execute(
        query.order_by(AgentProjectAuthRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = []

    for req in result.scalars().all():
        rows.append(await _request_to_response(req, db))

    return AgentProjectAuthRequestListResponse(
        requests=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


async def approve_project_auth_request(
    *,
    request_id: int,
    body: ApproveProjectAuthRequest,
    admin: Admin,
    db: AsyncSession,
) -> AgentProjectAuthRequestResponse:
    req = await _get_request_or_404(request_id, db)

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审核申请可以批准")

    now = _now()

    req.status = "approved"
    req.reviewed_by_admin_id = admin.id
    req.review_note = body.review_note
    req.reviewed_at = now
    req.updated_at = now

    await _grant_agent_project_auth(
        agent_id=req.agent_id,
        project_id=req.project_id,
        valid_until=body.valid_until,
        source="request_approved",
        request_id=req.id,
        admin_id=admin.id,
        reason=body.review_note,
        db=db,
    )

    await db.flush()
    await _refresh_request_for_response(req, db)

    return await _request_to_response(req, db)


async def reject_project_auth_request(
    *,
    request_id: int,
    body: RejectProjectAuthRequest,
    admin: Admin,
    db: AsyncSession,
) -> AgentProjectAuthRequestResponse:
    req = await _get_request_or_404(request_id, db)

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审核申请可以拒绝")

    now = _now()

    req.status = "rejected"
    req.reviewed_by_admin_id = admin.id
    req.review_note = body.review_note
    req.reviewed_at = now
    req.updated_at = now

    await db.flush()
    await _refresh_request_for_response(req, db)

    return await _request_to_response(req, db)


# ═══════════════════════════════════════════════════════════════
# 内部读取辅助
# ═══════════════════════════════════════════════════════════════

async def _load_policy_map(
    project_ids: list[int],
    db: AsyncSession,
) -> dict[int, ProjectAccessPolicy]:
    if not project_ids:
        return {}

    result = await db.execute(
        select(ProjectAccessPolicy).where(ProjectAccessPolicy.project_id.in_(project_ids))
    )

    return {
        policy.project_id: policy
        for policy in result.scalars().all()
    }


async def _load_price_map(
    project_ids: list[int],
    db: AsyncSession,
) -> dict[int, dict[str, float]]:
    if not project_ids:
        return {}

    result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id.in_(project_ids),
            ProjectPrice.user_level.in_(LEVEL_ORDER),
        )
    )

    data: dict[int, dict[str, float]] = {}

    for price in result.scalars().all():
        data.setdefault(price.project_id, {})[price.user_level] = _as_float(
            price.points_per_device
        )

    return data


async def _load_authorized_project_map(
    agent_id: int,
    db: AsyncSession,
    now: datetime,
) -> dict[int, AgentProjectAuth]:
    result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.status == "active",
        )
    )

    data: dict[int, AgentProjectAuth] = {}

    for item in result.scalars().all():
        if _is_future(item.valid_until, now):
            data[item.project_id] = item

    return data


async def _load_last_request_map(
    agent_id: int,
    db: AsyncSession,
) -> dict[int, AgentProjectAuthRequest]:
    result = await db.execute(
        select(AgentProjectAuthRequest)
        .where(AgentProjectAuthRequest.agent_id == agent_id)
        .order_by(AgentProjectAuthRequest.created_at.desc())
    )

    data: dict[int, AgentProjectAuthRequest] = {}

    for req in result.scalars().all():
        if req.project_id not in data:
            data[req.project_id] = req

    return data


async def _load_invite_project_ids(
    agent_id: int,
    db: AsyncSession,
) -> set[int]:
    result = await db.execute(
        select(AgentProjectAccessInvite.project_id).where(
            AgentProjectAccessInvite.agent_id == agent_id,
            AgentProjectAccessInvite.is_active == True,  # noqa: E712
        )
    )

    return {
        row[0]
        for row in result.all()
    }


async def _get_agent_available_points(
    agent_id: int,
    db: AsyncSession,
) -> Decimal:
    result = await db.execute(
        select(AgentBalance).where(AgentBalance.agent_id == agent_id)
    )

    balance = result.scalar_one_or_none()

    if not balance:
        return Decimal("0.00")

    return (
        Decimal(str(balance.charged_points or 0))
        + Decimal(str(balance.credit_points or 0))
        - Decimal(str(balance.frozen_credit or 0))
    )


# ═══════════════════════════════════════════════════════════════
# 内部规则判断
# ═══════════════════════════════════════════════════════════════

def _build_price_items(price_map: dict[str, float]) -> list[dict]:
    rows = []

    for level in LEVEL_ORDER:
        if level not in price_map:
            continue

        rows.append(
            {
                "level": level,
                "level_name": LEVEL_NAMES[level],
                "points": price_map.get(level),
                "unit_label": UNIT_LABELS[level],
            }
        )

    return rows


def _default_policy(project_id: int) -> ProjectAccessPolicy:
    return ProjectAccessPolicy(
        project_id=project_id,
        visibility_mode="public",
        open_mode="manual_review",
        min_visible_agent_level=1,
        min_apply_agent_level=1,
        min_auto_open_agent_level=None,
        min_available_points=0,
        allow_apply=True,
        allow_auto_open=False,
        require_request_reason=True,
        cooldown_hours_after_reject=24,
        is_active=True,
    )


async def _get_or_create_policy(
    project_id: int,
    db: AsyncSession,
) -> ProjectAccessPolicy:
    result = await db.execute(
        select(ProjectAccessPolicy).where(ProjectAccessPolicy.project_id == project_id)
    )

    policy = result.scalar_one_or_none()

    if policy:
        return policy

    policy = _default_policy(project_id)
    db.add(policy)
    await db.flush()
    await db.refresh(policy)

    return policy


def _is_project_visible(
    *,
    agent: Agent,
    policy: ProjectAccessPolicy,
    is_authorized: bool,
    is_invited: bool,
) -> bool:
    if is_authorized:
        return True

    if not policy.is_active:
        return False

    if policy.visibility_mode == "hidden":
        return False

    if policy.visibility_mode == "invite_only":
        return is_invited

    if policy.visibility_mode == "level_limited":
        return agent.level >= policy.min_visible_agent_level

    return True


def _can_apply(
    *,
    agent: Agent,
    policy: ProjectAccessPolicy,
) -> bool:
    if not policy.is_active:
        return False

    if not policy.allow_apply:
        return False

    if policy.open_mode == "disabled":
        return False

    return agent.level >= policy.min_apply_agent_level


def _can_auto_open(
    *,
    agent: Agent,
    policy: ProjectAccessPolicy,
    available_points: Decimal,
) -> bool:
    if not policy.is_active:
        return False

    if not policy.allow_auto_open:
        return False

    if policy.open_mode not in {"auto_by_level", "auto_by_condition"}:
        return False

    if policy.min_auto_open_agent_level is None:
        return False

    if agent.level < policy.min_auto_open_agent_level:
        return False

    if policy.open_mode == "auto_by_condition":
        if available_points < Decimal(str(policy.min_available_points or 0)):
            return False

    return True


def _build_auto_approve_reason(
    agent: Agent,
    policy: ProjectAccessPolicy,
    available_points: Decimal,
) -> str:
    return (
        f"自动开通：代理等级 Lv.{agent.level} 满足最低自动开通等级 "
        f"Lv.{policy.min_auto_open_agent_level}；"
        f"开通模式={policy.open_mode}；"
        f"当前可用点数={available_points:.2f}。"
    )


def _validate_policy(policy: ProjectAccessPolicy) -> None:
    if policy.allow_auto_open and policy.open_mode not in {"auto_by_level", "auto_by_condition"}:
        raise HTTPException(
            status_code=400,
            detail="允许自动开通时，open_mode 必须是 auto_by_level 或 auto_by_condition",
        )

    if policy.open_mode in {"auto_by_level", "auto_by_condition"} and policy.min_auto_open_agent_level is None:
        raise HTTPException(
            status_code=400,
            detail="自动开通模式下必须设置最低自动开通代理等级",
        )

    if policy.min_apply_agent_level < policy.min_visible_agent_level:
        raise HTTPException(
            status_code=400,
            detail="最低申请代理等级不能低于最低可见代理等级",
        )

    if policy.visibility_mode == "hidden":
        policy.allow_apply = False
        policy.allow_auto_open = False
        policy.open_mode = "disabled"
        policy.min_auto_open_agent_level = None


# ═══════════════════════════════════════════════════════════════
# 内部实体读取 / 写入
# ═══════════════════════════════════════════════════════════════

async def _get_project_or_404(
    project_id: int,
    db: AsyncSession,
) -> GameProject:
    result = await db.execute(
        select(GameProject).where(
            GameProject.id == project_id,
            GameProject.is_active == True,  # noqa: E712
        )
    )

    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="项目不存在或已停用")

    return project


async def _get_active_agent_project_auth(
    agent_id: int,
    project_id: int,
    db: AsyncSession,
    now: datetime,
) -> AgentProjectAuth | None:
    result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.project_id == project_id,
            AgentProjectAuth.status == "active",
        )
    )

    auth = result.scalar_one_or_none()

    if not auth:
        return None

    if not _is_future(auth.valid_until, now):
        return None

    return auth


async def _get_pending_request(
    agent_id: int,
    project_id: int,
    db: AsyncSession,
) -> AgentProjectAuthRequest | None:
    result = await db.execute(
        select(AgentProjectAuthRequest).where(
            AgentProjectAuthRequest.agent_id == agent_id,
            AgentProjectAuthRequest.project_id == project_id,
            AgentProjectAuthRequest.status == "pending",
        )
    )

    return result.scalar_one_or_none()


async def _get_request_or_404(
    request_id: int,
    db: AsyncSession,
) -> AgentProjectAuthRequest:
    result = await db.execute(
        select(AgentProjectAuthRequest).where(
            AgentProjectAuthRequest.id == request_id
        )
    )

    req = result.scalar_one_or_none()

    if not req:
        raise HTTPException(status_code=404, detail="项目授权申请不存在")

    return req


async def _grant_agent_project_auth(
    *,
    agent_id: int,
    project_id: int,
    valid_until: datetime | None,
    source: str,
    request_id: int | None,
    admin_id: int | None,
    reason: str | None,
    db: AsyncSession,
) -> AgentProjectAuth:
    """
    写入 / 更新代理项目授权。

    注意:
        这里使用 ORM 字段赋值，不使用裸 SQL。
        前提是 AgentProjectAuth ORM 模型已经包含:
            source
            request_id
            granted_by_admin_id
            granted_reason
    """
    if source not in {"admin_manual", "request_approved", "auto_approved"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法项目授权来源: {source}",
        )

    normalized_valid_until = _ensure_aware(valid_until)

    result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.project_id == project_id,
        )
    )

    auth = result.scalar_one_or_none()

    if auth:
        auth.status = "active"
        auth.valid_until = normalized_valid_until
        auth.source = source
        auth.request_id = request_id
        auth.granted_by_admin_id = admin_id
        auth.granted_reason = reason
    else:
        auth = AgentProjectAuth(
            agent_id=agent_id,
            project_id=project_id,
            valid_until=normalized_valid_until,
            status="active",
            source=source,
            request_id=request_id,
            granted_by_admin_id=admin_id,
            granted_reason=reason,
        )
        db.add(auth)

    await db.flush()
    await db.refresh(auth)

    return auth


# ═══════════════════════════════════════════════════════════════
# 响应构造
# ═══════════════════════════════════════════════════════════════

def _policy_to_response(
    policy: ProjectAccessPolicy,
    project: GameProject,
) -> ProjectAccessPolicyResponse:
    return ProjectAccessPolicyResponse(
        id=policy.id,
        project_id=policy.project_id,
        project_name=project.display_name,
        project_code=project.code_name,
        project_type=project.project_type,
        visibility_mode=policy.visibility_mode,
        open_mode=policy.open_mode,
        min_visible_agent_level=policy.min_visible_agent_level,
        min_apply_agent_level=policy.min_apply_agent_level,
        min_auto_open_agent_level=policy.min_auto_open_agent_level,
        min_available_points=_as_float(policy.min_available_points),
        allow_apply=policy.allow_apply,
        allow_auto_open=policy.allow_auto_open,
        require_request_reason=policy.require_request_reason,
        cooldown_hours_after_reject=policy.cooldown_hours_after_reject,
        is_active=policy.is_active,
    )


async def _request_to_response(
    req: AgentProjectAuthRequest,
    db: AsyncSession,
) -> AgentProjectAuthRequestResponse:
    """
    将 AgentProjectAuthRequest 转为响应对象。

    关键规则:
        不要在构造响应时直接反复访问可能 expired 的 ORM 字段。
        先把 req 的字段复制到局部变量。
        然后再 await db.get(...) 查询关联信息。
    """
    request_id = req.id
    agent_id = req.agent_id
    project_id = req.project_id

    request_reason = req.request_reason
    request_status = req.status

    reviewed_by_admin_id = req.reviewed_by_admin_id
    review_note = req.review_note
    reviewed_at = req.reviewed_at
    auto_approve_reason = req.auto_approve_reason

    created_at = req.created_at
    updated_at = req.updated_at

    agent = await db.get(Agent, agent_id)
    project = await db.get(GameProject, project_id)
    admin = await db.get(Admin, reviewed_by_admin_id) if reviewed_by_admin_id else None

    return AgentProjectAuthRequestResponse(
        id=request_id,
        agent_id=agent_id,
        agent_username=agent.username if agent else None,
        agent_level=agent.level if agent else None,

        project_id=project_id,
        project_name=project.display_name if project else None,
        project_code=project.code_name if project else None,

        request_reason=request_reason,
        status=request_status,

        reviewed_by_admin_id=reviewed_by_admin_id,
        reviewed_by_admin_username=admin.username if admin else None,
        review_note=review_note,
        reviewed_at=reviewed_at,
        auto_approve_reason=auto_approve_reason,

        created_at=created_at,
        updated_at=updated_at,
    )