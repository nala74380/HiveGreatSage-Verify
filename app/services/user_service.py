r"""
文件位置: app/services/user_service.py
文件名称: user_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.4.1
功能说明:
    用户管理服务层。

核心口径:
    - 用户 User 是账号主体。
    - 用户等级、授权设备数、到期时间不再以 User 为主口径。
    - 项目内等级、项目授权设备数、项目到期时间统一归属 Authorization。
    - 一个用户可以在 A 项目是普通，在 B 项目是 VIP。
    - 一个用户可以在不同项目拥有不同授权设备数和不同到期时间。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。

本版修复:
    - 已激活设备数从 DeviceBinding 统计。
    - LoginLog 只作为登录审计，不再作为设备名额占用依据。
    - PC 中控登录不会再误占用安卓脚本激活名额。

安全边界:
    - 不查询旧密码明文。
    - 管理员自动生成密码时，只在响应中一次性返回新密码。
    - 代理不能自动生成并查看明文，只能手动修改密码。
    - 删除用户只做软删除，保留授权、设备、流水等审计数据。
    - 删除用户返点只处理存在授权扣点快照的代理扣点授权。
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.utils import generate_password as _generate_password, get_project_or_404 as _get_project_or_404
from app.models.main.models import (
    Admin,
    Agent,
    AgentProjectAuth,
    Authorization,
    DeviceBinding,
    GameProject,
    User,
)
from app.models.main.accounting import AccountingWallet
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationInfo,
    AuthorizationResponse,
    AuthorizationUpdateRequest,
    AuthorizationUpgradePreviewResponse,
    CreatorAgentDetailResponse,
    UserCreateRequest,
    UserListResponse,
    UserPasswordUpdateRequest,
    UserPasswordUpdateResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.accounting_service import (
    BILLING_RULES,
    LEVEL_NAMES,
    _ceil_hours,
    calculate_authorization_cost,
    consume_agent_authorization_points,
    refund_user_authorization_points_on_delete,
)


# ═══════════════════════════════════════════════════════════════
# 用户基础操作
# ═══════════════════════════════════════════════════════════════

async def create_user(
    body: UserCreateRequest,
    db: AsyncSession,
    admin: Admin | None,
    agent: Agent | None,
) -> UserResponse:
    """
    创建用户。

    新业务口径:
      - 创建用户只创建账号主体。
      - 用户数量只作为统计展示。
      - 项目等级、设备数、到期时间在项目授权时设置。
      - 代理真正的商业约束发生在项目授权和扣点阶段。
    """
    await _assert_username_unique(body.username, db)

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),

        # 兼容旧字段，新页面不再主展示。
        created_by_admin=admin is not None,
        created_by_agent_id=agent.id if agent else None,
        status="active",
    )

    db.add(user)
    await db.flush()

    return _user_to_response(
        user=user,
        authorizations=[],
        creator_agent_username=agent.username if agent else None,
    )


async def list_users(
    db: AsyncSession,
    admin: Admin | None,
    agent: Agent | None,
    page: int,
    page_size: int,
    status_filter: str | None,
    level_filter: str | None,
    project_id_filter: int | None = None,
    creator_agent_id_filter: int | None = None,
) -> UserListResponse:
    """
    查询用户列表。

    过滤规则:
      - status：过滤 User.status。
      - level：过滤 Authorization.user_level。
      - project_id：过滤 Authorization.game_project_id。
      - creator_agent_id：管理员查看指定代理创建的用户。
    """
    query = select(User).where(User.is_deleted == False)  # noqa: E712

    if agent is not None:
        query = query.where(User.created_by_agent_id == agent.id)

    if admin is not None and creator_agent_id_filter:
        query = query.where(User.created_by_agent_id == creator_agent_id_filter)

    if status_filter:
        query = query.where(User.status == status_filter)

    if level_filter or project_id_filter:
        auth_subq = select(Authorization.user_id).where(
            Authorization.status == "active",
        )

        if level_filter:
            auth_subq = auth_subq.where(Authorization.user_level == level_filter)

        if project_id_filter:
            auth_subq = auth_subq.where(Authorization.game_project_id == project_id_filter)

        query = query.where(User.id.in_(auth_subq))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(User.id.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()

    if not users:
        return UserListResponse(
            users=[],
            total=total,
            page=page,
            page_size=page_size,
        )

    creator_agent_map = await _load_creator_agent_map(users, db)

    auth_details_map = await _load_authorization_details_map(
        users=users,
        only_active=True,
        db=db,
        project_id_filter=project_id_filter,
    )

    user_ids = [u.id for u in users]

    auth_total_result = await db.execute(
        select(Authorization.user_id, func.count(Authorization.id).label("cnt"))
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.user_id)
    )
    auth_total_map = {
        row.user_id: row.cnt
        for row in auth_total_result.all()
    }

    return UserListResponse(
        users=[
            _user_to_response(
                user=u,
                authorizations=auth_details_map.get(u.id, []),
                authorization_count=auth_total_map.get(u.id, 0),
                active_authorization_count=len([
                    item
                    for item in auth_details_map.get(u.id, [])
                    if item.status == "active" and not item.is_expired
                ]),
                active_project_names=[
                    item.game_project_name
                    for item in auth_details_map.get(u.id, [])
                    if item.status == "active" and not item.is_expired
                ],
                creator_agent_username=creator_agent_map.get(u.created_by_agent_id),
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_user(
    user_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
    project_id_filter: int | None = None,
) -> UserResponse:
    """查询用户详情。"""
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    creator_agent_username = None
    if user.created_by_agent_id:
        result = await db.execute(
            select(Agent.username).where(Agent.id == user.created_by_agent_id)
        )
        creator_agent_username = result.scalar_one_or_none()

    auth_details_map = await _load_authorization_details_map(
        users=[user],
        only_active=False,
        db=db,
        project_id_filter=project_id_filter,
    )

    authorizations = auth_details_map.get(user.id, [])

    return _user_to_response(
        user=user,
        authorizations=authorizations,
        authorization_count=len(authorizations),
        active_authorization_count=len([
            item
            for item in authorizations
            if item.status == "active" and not item.is_expired
        ]),
        active_project_names=[
            item.game_project_name
            for item in authorizations
            if item.status == "active" and not item.is_expired
        ],
        creator_agent_username=creator_agent_username,
    )


async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> UserResponse:
    """
    更新用户基础信息。

    注意:
      - 项目内等级、授权设备数、到期时间不在这里更新。
      - 这些字段通过 update_authorization 更新。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    if body.status is not None:
        user.status = body.status

    await db.flush()
    await db.refresh(user)

    return await get_user(
        user_id=user_id,
        db=db,
        admin=admin,
        agent=agent,
    )


async def update_user_password(
    user_id: int,
    body: UserPasswordUpdateRequest,
    db: AsyncSession,
    admin: Admin | None,
    agent: Agent | None,
) -> UserPasswordUpdateResponse:
    """
    修改/重置用户密码。

    - 管理员可 auto_generate，并一次性返回 generated_password。
    - 代理不能 auto_generate 获取明文，只能提交 new_password。
    - 系统只保存 password_hash。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    generated_password: str | None = None

    if body.auto_generate:
        if admin is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有管理员可以自动生成并一次性查看新密码",
            )
        generated_password = _generate_password()
        new_password = generated_password
    else:
        if not body.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请输入新密码",
            )
        new_password = body.new_password

    user.password_hash = hash_password(new_password)
    await db.flush()

    return UserPasswordUpdateResponse(
        user_id=user.id,
        username=user.username,
        message="密码已更新",
        generated_password=generated_password,
    )


async def soft_delete_user(
    user_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> None:
    """
    软删除用户。

    规则:
      - 管理员可以删除所有用户。
      - 代理只能删除自己创建的用户。
      - 只做软删除 is_deleted=True，不物理删除数据。
      - 授权记录、设备记录、流水记录保留，便于后续审计。
      - 删除前先按授权扣点快照自动返点。
      - 返点只处理代理实际扣过点且未过期的授权。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    delete_time = datetime.now(timezone.utc)

    await refund_user_authorization_points_on_delete(
        user_id=user.id,
        db=db,
        delete_time=delete_time,
    )

    auth_result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user.id,
            Authorization.status == "active",
        )
    )
    for auth_item in auth_result.scalars().all():
        auth_item.status = "suspended"

    user.is_deleted = True
    user.status = "suspended"
    await db.flush()


# ═══════════════════════════════════════════════════════════════
# 项目授权
# ═══════════════════════════════════════════════════════════════

async def grant_authorization(
    user_id: int,
    body: AuthorizationCreateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """
    为用户授予指定项目权限。

    新业务口径:
      - user_level 属于 Authorization。
      - authorized_devices 属于 Authorization。
      - valid_until 属于 Authorization。

    代理授权规则:
      - 只能给自己创建的用户授权。
      - 只能授权自己已有权限的项目。
      - 必须设置 valid_until。
      - authorized_devices 必须大于 0。
      - 授权成功前必须完成扣点。
      - 授权扣点成功后保存授权扣点快照。
      - 已 active 授权不允许代理用 POST 覆盖，避免账务补扣复杂化。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    project = await _get_project_or_404(body.game_project_id, db)

    if body.user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别授权只有管理员可以设置",
        )

    if agent is not None:
        if body.valid_until is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理授权项目必须设置到期时间，不能永久有效",
            )

        if body.authorized_devices <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理授权设备数必须大于 0",
            )

        agent_project_auth_result = await db.execute(
            select(AgentProjectAuth).where(
                AgentProjectAuth.agent_id == agent.id,
                AgentProjectAuth.project_id == body.game_project_id,
                AgentProjectAuth.status == "active",
            )
        )
        if not agent_project_auth_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"代理没有项目「{project.display_name}」的授权权限",
            )

    existing_result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user_id,
            Authorization.game_project_id == body.game_project_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if agent is not None and existing and existing.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户已授权此项目。代理修改等级/设备数/续期涉及补扣点，请由管理员处理或后续走专用续费接口。",
        )

    now = datetime.now(timezone.utc)
    consumed_points = 0.0

    if existing:
        existing.status = "active"
        existing.user_level = body.user_level
        existing.authorized_devices = body.authorized_devices
        existing.valid_from = now
        existing.valid_until = body.valid_until
        auth = existing
    else:
        auth = Authorization(
            user_id=user_id,
            game_project_id=body.game_project_id,
            user_level=body.user_level,
            authorized_devices=body.authorized_devices,
            valid_from=now,
            valid_until=body.valid_until,
            status="active",
        )
        db.add(auth)

    await db.flush()

    if agent is not None:
        consume_result = await consume_agent_authorization_points(
            agent_id=agent.id,
            user_id=user.id,
            project_id=project.id,
            authorization_id=auth.id,
            user_level=body.user_level,
            authorized_devices=body.authorized_devices,
            start_at=now,
            valid_until=body.valid_until,
            db=db,
        )
        consumed_points = float(consume_result.get("total_cost") or 0.0)

    await db.flush()

    return _authorization_to_response(
        auth=auth,
        project=project,
        consumed_points=consumed_points,
    )


async def update_authorization(
    user_id: int,
    auth_id: int,
    body: AuthorizationUpdateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """
    修改用户项目授权。

    当前安全策略:
      - 管理员可以修改等级、设备数、到期时间、状态。
      - 代理暂不允许修改已授权项目，避免账务补扣/退款规则未定导致错账。
      - 管理员修改授权当前不生成授权扣点快照。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)

    # 代理只能升级设备数，不能改等级和状态
    if admin is None and agent is not None:
        if body.user_level is not None and body.user_level != auth.user_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="代理不能修改授权等级，请联系管理员处理",
            )
        if body.status is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="代理不能修改授权状态，请联系管理员处理",
            )
        # 只能增加设备数
        if body.authorized_devices is not None and body.authorized_devices < int(auth.authorized_devices or 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理不能减少授权设备数",
            )

    consumed_points = 0.0

    if body.user_level is not None:
        auth.user_level = body.user_level

    if body.authorized_devices is not None:
        old_devices = int(auth.authorized_devices or 0)
        new_devices = int(body.authorized_devices)
        auth.authorized_devices = new_devices

        # 代理升级设备数时扣点
        if agent is not None and new_devices > old_devices:
            additional = new_devices - old_devices
            cost = await calculate_authorization_cost(
                project_id=project.id, user_level=auth.user_level,
                authorized_devices=additional,
                start_at=datetime.now(timezone.utc),
                valid_until=auth.valid_until,
                db=db,
            )
            consumed_points = float(cost.get("total_cost") or 0.0)
            if consumed_points > 0:
                await consume_agent_authorization_points(
                    agent_id=agent.id, user_id=user.id, project_id=project.id,
                    authorization_id=auth.id, user_level=auth.user_level,
                    authorized_devices=additional,
                    start_at=datetime.now(timezone.utc),
                    valid_until=auth.valid_until,
                    db=db,
                )

    if "valid_until" in body.model_fields_set:
        auth.valid_until = body.valid_until

    if body.status is not None:
        auth.status = body.status

    await db.flush()

    return _authorization_to_response(
        auth=auth,
        project=project,
        consumed_points=consumed_points,
    )


async def revoke_authorization(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> None:
    """撤销授权。当前规则：单独停用授权不退款；删除用户时才按规则自动返点。"""
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
    )
    auth.status = "suspended"
    await db.flush()


async def preview_authorization_upgrade(
    user_id: int,
    auth_id: int,
    additional_devices: int,
    mode: str,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationUpgradePreviewResponse:
    """预览授权升级结果。

    该函数是授权升级预览的唯一业务入口。
    Router 只负责鉴权和参数接收，不再直接拼计费逻辑。
    """
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)

    old_devices = int(auth.authorized_devices or 0)
    new_devices = old_devices + additional_devices
    now = datetime.now(timezone.utc)

    if auth.valid_until and _ensure_aware(auth.valid_until) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权已到期，请重新授权")

    level_rule = BILLING_RULES.get(auth.user_level, {})
    period_hours = int(level_rule.get("period_hours", 720))
    valid_until_for_cost = auth.valid_until

    if mode == "average":
        old_remaining = _ceil_hours(now, auth.valid_until) if auth.valid_until else 0
        new_devices_hours = additional_devices * period_hours
        avg_hours = int((old_devices * old_remaining + new_devices_hours) / new_devices)
        valid_until_for_cost = now + timedelta(hours=avg_hours)

    if agent is not None:
        cost = await calculate_authorization_cost(
            project_id=project.id,
            user_level=auth.user_level,
            authorized_devices=additional_devices,
            start_at=now,
            valid_until=valid_until_for_cost,
            db=db,
        )
        consumed_points = float(cost.get("total_cost") or 0.0)
        unit_price = float(cost.get("unit_price") or 0.0)
        period_hours = int(cost.get("billing_period_hours") or period_hours)
    else:
        consumed_points = 0.0
        unit_price = 0.0

    return AuthorizationUpgradePreviewResponse(
        old_devices=old_devices,
        new_devices=new_devices,
        additional_devices=additional_devices,
        mode=mode,
        consumed_points=consumed_points,
        new_expiry=valid_until_for_cost,
        unit_price=unit_price,
        period_hours=period_hours,
    )


async def upgrade_authorization(
    user_id: int,
    auth_id: int,
    body: "AuthorizationUpgradeRequest",
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> "AuthorizationUpgradeResponse":
    """
    升级授权设备数。

    追加模式：新设备继承旧到期，按剩余时长比例扣点。
    平均模式：旧剩余点数 + 新购点数 → 统一折算为新到期时间。
    管理端操作不走扣点。
    """
    from app.schemas.user import AuthorizationUpgradeRequest, AuthorizationUpgradeResponse

    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)

    old_devices = int(auth.authorized_devices or 0)
    new_devices = old_devices + body.additional_devices
    now = datetime.now(timezone.utc)

    # 检查到期
    if auth.valid_until and _ensure_aware(auth.valid_until) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权已到期，请重新授权")

    consumed_points = 0.0

    if body.mode == "average":
        # 平均模式：新到期 = 加权平均
        if auth.valid_until:
            old_remaining = _ceil_hours(now, auth.valid_until)
        else:
            old_remaining = 0
        period_hours = BILLING_RULES.get(auth.user_level, {}).get("period_hours", 720)
        new_devices_hours = body.additional_devices * period_hours
        avg_hours = int((old_devices * old_remaining + new_devices_hours) / new_devices)
        auth.valid_until = now + timedelta(hours=avg_hours)

        if agent is not None:
            cost = await calculate_authorization_cost(
                project_id=project.id, user_level=auth.user_level,
                authorized_devices=body.additional_devices,
                start_at=now, valid_until=auth.valid_until, db=db,
            )
            consumed_points = cost["total_cost"]
            await consume_agent_authorization_points(
                agent_id=agent.id, user_id=user.id, project_id=project.id,
                authorization_id=auth.id, user_level=auth.user_level,
                authorized_devices=body.additional_devices,
                start_at=now, valid_until=auth.valid_until, db=db,
            )
    else:
        # 追加模式：到期不变
        if agent is not None and auth.valid_until:
            # 按剩余比例计算
            remaining = _ceil_hours(now, auth.valid_until)
            level_rule = BILLING_RULES.get(auth.user_level, {})
            period_hours = level_rule.get("period_hours", 720)
            periods = max(1, (remaining + period_hours - 1) // period_hours)
            # 取单价
            from app.models.main.models import ProjectPrice
            price_result = await db.execute(
                select(ProjectPrice).where(
                    ProjectPrice.project_id == project.id,
                    ProjectPrice.user_level == auth.user_level,
                )
            )
            price = price_result.scalar_one_or_none()
            if not price:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"项目未设置 {auth.user_level} 级别定价")

            from decimal import Decimal
            unit_price = Decimal(str(price.points_per_device))
            total_cost = unit_price * Decimal(str(body.additional_devices)) * Decimal(str(periods))
            consumed_points = float(total_cost)

            await consume_agent_authorization_points(
                agent_id=agent.id, user_id=user.id, project_id=project.id,
                authorization_id=auth.id, user_level=auth.user_level,
                authorized_devices=body.additional_devices,
                start_at=now, valid_until=auth.valid_until, db=db,
            )

    auth.authorized_devices = new_devices
    await db.flush()

    return AuthorizationUpgradeResponse(
        authorization=_authorization_to_response(auth, project, consumed_points),
        consumed_points=consumed_points,
        mode=body.mode,
        old_devices=old_devices,
        new_devices=new_devices,
        new_expiry=auth.valid_until,
    )


# ═══════════════════════════════════════════════════════════════
# 创建者详情
# ═══════════════════════════════════════════════════════════════

async def get_creator_agent_detail(
    agent_id: int,
    db: AsyncSession,
    admin: Admin | None,
    page: int = 1,
    page_size: int = 200,
) -> CreatorAgentDetailResponse:
    """管理员查看某个代理创建者详情及其创建的用户。"""
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以查看创建者详情",
        )

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"代理 ID={agent_id} 不存在",
        )

    user_list = await list_users(
        db=db,
        admin=admin,
        agent=None,
        page=page,
        page_size=page_size,
        status_filter=None,
        level_filter=None,
        project_id_filter=None,
        creator_agent_id_filter=agent_id,
    )

    balance_result = await db.execute(
        select(AccountingWallet).where(AccountingWallet.agent_id == agent_id)
    )
    wallet = balance_result.scalar_one_or_none()

    auth_result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.status == "active",
        )
        .order_by(GameProject.display_name)
    )

    authorized_projects = [
        {
            "project_id": project.id,
            "code_name": project.code_name,
            "display_name": project.display_name,
            "project_type": project.project_type,
            "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
            "status": auth.status,
        }
        for auth, project in auth_result.all()
    ]

    agent_payload = {
        "id": agent.id,
        "username": agent.username,
        "level": agent.hierarchy_depth,
        "status": agent.status,
        "commission_rate": float(agent.commission_rate) if agent.commission_rate is not None else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "authorized_projects": authorized_projects,
        "balance": {
            "charged_points": float(wallet.charged_balance) if wallet else 0.0,
            "credit_points": float(wallet.credit_balance) if wallet else 0.0,
            "frozen_credit": float(wallet.frozen_credit) if wallet else 0.0,
            "available_total": float(wallet.available_total) if wallet else 0.0,
        },
        "users_total": user_list.total,
    }

    return CreatorAgentDetailResponse(
        agent=agent_payload,
        users=user_list.users,
    )


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

async def _get_user_or_404(user_id: int, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID={user_id} 不存在",
        )

    return user



async def _get_authorization_or_404(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
) -> Authorization:
    result = await db.execute(
        select(Authorization).where(
            Authorization.id == auth_id,
            Authorization.user_id == user_id,
        )
    )
    auth = result.scalar_one_or_none()

    if not auth:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授权记录不存在",
        )

    return auth


async def _assert_username_unique(username: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{username}' 已存在",
        )


def _assert_can_access_user(
    user: User,
    admin: Admin | None,
    agent: Agent | None,
) -> None:
    if admin is not None:
        return

    if agent is not None and user.created_by_agent_id == agent.id:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="无权访问该用户",
    )


def _user_to_response(
    user: User,
    authorizations: list[AuthorizationInfo],
    authorization_count: int = 0,
    active_authorization_count: int = 0,
    active_project_names: list[str] | None = None,
    creator_agent_username: str | None = None,
) -> UserResponse:
    if user.created_by_agent_id:
        created_by_type = "agent"
        created_by_display = creator_agent_username or f"代理ID={user.created_by_agent_id}"
    elif user.created_by_admin:
        created_by_type = "admin"
        created_by_display = "管理员"
    else:
        created_by_type = "unknown"
        created_by_display = "未知"

    return UserResponse(
        id=user.id,
        username=user.username,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,

        created_by_admin=user.created_by_admin,
        created_by_agent_id=user.created_by_agent_id,
        created_by_type=created_by_type,
        created_by_display=created_by_display,
        created_by_agent_username=creator_agent_username,

        # 兼容旧字段。
        authorizations=authorizations,
        authorization_count=authorization_count,
        active_authorization_count=active_authorization_count,
        active_project_names=active_project_names or [],
    )


def _authorization_to_response(
    auth: Authorization,
    project: GameProject,
    consumed_points: float = 0.0,
) -> AuthorizationResponse:
    return AuthorizationResponse(
        id=auth.id,
        user_id=auth.user_id,
        game_project_id=project.id,
        game_project_code=project.code_name,
        game_project_name=project.display_name,
        user_level=auth.user_level,
        authorized_devices=auth.authorized_devices,
        valid_from=auth.valid_from,
        valid_until=auth.valid_until,
        status=auth.status,
        consumed_points=consumed_points,
    )


async def _load_creator_agent_map(
    users: list[User],
    db: AsyncSession,
) -> dict[int, str]:
    agent_ids = sorted({
        user.created_by_agent_id
        for user in users
        if user.created_by_agent_id
    })

    if not agent_ids:
        return {}

    result = await db.execute(
        select(Agent.id, Agent.username).where(Agent.id.in_(agent_ids))
    )

    return {
        row.id: row.username
        for row in result.all()
    }


async def _load_project_activation_count_map(
    user_ids: list[int],
    db: AsyncSession,
) -> dict[tuple[int, int], int]:
    """
    统计每个用户在每个项目下真实占用的激活设备数。

    核心口径:
      - 已激活设备数必须来自 DeviceBinding。
      - DeviceBinding 是用户 × 项目 × 设备维度。
      - 只有 status='active' 的设备绑定才占用授权设备名额。
      - PC 中控登录只写 LoginLog，不创建 DeviceBinding，因此不占用设备名额。
      - LoginLog 只作为登录审计，不再作为激活设备统计来源。

    修复问题:
      旧实现按 LoginLog.success + distinct device_fingerprint 统计。
      这会把 PC 中控登录也误算成已激活设备，导致：
        用户列表显示已激活 1，
        但设备详情中没有真实设备。
    """
    if not user_ids:
        return {}

    result = await db.execute(
        select(
            DeviceBinding.user_id,
            DeviceBinding.game_project_id,
            func.count(func.distinct(DeviceBinding.device_fingerprint)).label("cnt"),
        )
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
            DeviceBinding.game_project_id.is_not(None),
        )
        .group_by(
            DeviceBinding.user_id,
            DeviceBinding.game_project_id,
        )
    )

    return {
        (row.user_id, row.game_project_id): int(row.cnt or 0)
        for row in result.all()
    }


async def _load_authorization_details_map(
    users: list[User],
    only_active: bool,
    db: AsyncSession,
    project_id_filter: int | None = None,
) -> dict[int, list[AuthorizationInfo]]:
    if not users:
        return {}

    user_ids = [user.id for user in users]

    query = (
        select(Authorization, GameProject)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(Authorization.user_id.in_(user_ids))
        .order_by(Authorization.user_id, GameProject.display_name)
    )

    if only_active:
        query = query.where(Authorization.status == "active")

    if project_id_filter:
        query = query.where(Authorization.game_project_id == project_id_filter)

    activation_map = await _load_project_activation_count_map(user_ids, db)

    result = await db.execute(query)
    rows = result.all()

    now = datetime.now(timezone.utc)
    data: dict[int, list[AuthorizationInfo]] = {}

    for auth, project in rows:
        authorized_devices = int(auth.authorized_devices or 0)
        activated_devices = int(
            activation_map.get((auth.user_id, auth.game_project_id), 0)
        )

        if authorized_devices == 0:
            inactive_devices = None
        else:
            inactive_devices = max(authorized_devices - activated_devices, 0)

        is_expired = False
        if auth.valid_until is not None:
            is_expired = _ensure_aware(auth.valid_until) < now

        item = AuthorizationInfo(
            id=auth.id,
            game_project_id=auth.game_project_id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            project_type=project.project_type,

            user_level=auth.user_level,
            user_level_name=LEVEL_NAMES.get(auth.user_level, auth.user_level),

            authorized_devices=authorized_devices,
            activated_devices=activated_devices,
            inactive_devices=inactive_devices,

            valid_from=auth.valid_from,
            valid_until=auth.valid_until,
            status=auth.status,
            is_expired=is_expired,
        )

        data.setdefault(auth.user_id, []).append(item)

    return data


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
