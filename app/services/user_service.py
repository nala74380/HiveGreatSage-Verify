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
from decimal import Decimal, ROUND_UP

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
    ProjectPrice,
    User,
)
from app.models.main.accounting import (
    AccountingWallet,
    AuthorizationChargeSnapshot,
    AuthorizationFreezeRecord,
)
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationCostPreviewResponse,
    AuthorizationInfo,
    AuthorizationLevelUpgradePreviewResponse,
    AuthorizationLevelUpgradeRequest,
    AuthorizationLevelUpgradeResponse,
    AuthorizationRenewPreviewResponse,
    AuthorizationRenewRequest,
    AuthorizationRenewResponse,
    AuthorizationResponse,
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
    consume_agent_authorization_level_upgrade_diff_points,
    consume_agent_authorization_points,
    consume_agent_authorization_topup_points,
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
      - 授权治理必须走专用动作接口（新增设备/续费/等级升级/停用/启用）。
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
      - 代理不允许删除用户账户，只能停用用户或停用项目授权。
      - 只做软删除 is_deleted=True，不物理删除数据。
      - 授权记录、设备记录、流水记录保留，便于后续审计。
      - 管理员删除前先按授权扣点快照自动返点。
      - 返点只处理代理实际扣过点且未过期的授权。
    """
    if agent is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理不允许删除用户账户，请停用用户或停用项目授权",
        )

    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    delete_time = datetime.now(timezone.utc)

    await refund_user_authorization_points_on_delete(
        user_id=user.id,
        db=db,
        delete_time=delete_time,
    )
    await settle_authorization_freezes_on_user_delete(
        user_id=user.id,
        db=db,
        admin=admin,
        settled_at=delete_time,
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

        await _assert_agent_project_auth_valid(
            db=db,
            agent=agent,
            project_id=body.game_project_id,
            project_name=project.display_name,
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

    if existing and existing.status == "suspended":
        frozen_result = await db.execute(
            select(AuthorizationFreezeRecord).where(
                AuthorizationFreezeRecord.authorization_id == existing.id,
                AuthorizationFreezeRecord.status == "frozen",
            )
        )
        if frozen_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该授权已停用并冻结权益，请走启用恢复接口，不要重新授权覆盖",
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


async def preview_authorization_cost(
    user_id: int,
    body: AuthorizationCreateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationCostPreviewResponse:
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    project = await _get_project_or_404(body.game_project_id, db)

    if body.user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别授权只有管理员可以预览和设置",
        )
    if body.valid_until is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="授权扣点预览必须设置到期时间",
        )

    if agent is not None:
        if body.authorized_devices <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理授权预览设备数必须大于 0",
            )
        await _assert_agent_project_auth_valid(
            db=db,
            agent=agent,
            project_id=body.game_project_id,
            project_name=project.display_name,
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
            detail="该用户已授权此项目，代理请走新增设备/续费/升级专用预览",
        )
    if existing and existing.status == "suspended":
        frozen_result = await db.execute(
            select(AuthorizationFreezeRecord).where(
                AuthorizationFreezeRecord.authorization_id == existing.id,
                AuthorizationFreezeRecord.status == "frozen",
            )
        )
        if frozen_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该授权已停用并冻结权益，请走启用恢复接口",
            )

    now = datetime.now(timezone.utc)
    cost = await calculate_authorization_cost(
        project_id=project.id,
        user_level=body.user_level,
        authorized_devices=body.authorized_devices,
        start_at=now,
        valid_until=body.valid_until,
        db=db,
    )

    wallet_snapshot = _empty_wallet_preview_snapshot()
    if agent is not None:
        wallet_snapshot = await _build_agent_wallet_preview_snapshot(
            db=db,
            agent_id=agent.id,
            total_cost=float(cost["total_cost"]),
        )

    return AuthorizationCostPreviewResponse(
        user_id=user.id,
        game_project_id=project.id,
        game_project_code=project.code_name,
        game_project_name=project.display_name,
        user_level=body.user_level,
        user_level_name=cost["level_name"],
        authorized_devices=body.authorized_devices,
        valid_until=body.valid_until,
        unit_price=float(cost["unit_price"]),
        period_count=int(cost["period_count"]),
        billing_period=cost["billing_period"],
        billing_period_name=cost["billing_period_name"],
        billing_period_hours=int(cost["billing_period_hours"]),
        paid_hours=int(cost["paid_hours"]),
        unit_label=cost["unit_label"],
        total_cost=float(cost["total_cost"]),
        will_charge=agent is not None,
        agent_id=agent.id if agent else None,
        **wallet_snapshot,
    )


async def revoke_authorization(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> None:
    """兼容旧 DELETE 路由：停用授权并写冻结权益记录。"""
    await suspend_authorization_with_freeze(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
        admin=admin,
        agent=agent,
    )


async def suspend_authorization_with_freeze(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """停用授权并冻结剩余权益；不返点、不改钱包、不写账本。"""
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
    )

    if auth.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有 active 授权可以停用",
        )

    project = await _get_project_or_404(auth.game_project_id, db)
    now = datetime.now(timezone.utc)
    remaining_hours = _authorization_remaining_hours(auth=auth, now=now)
    estimated_points = await _estimate_authorization_remaining_points(
        auth=auth,
        remaining_hours=remaining_hours,
        db=db,
    )

    existing_freeze_result = await db.execute(
        select(AuthorizationFreezeRecord).where(
            AuthorizationFreezeRecord.authorization_id == auth.id,
            AuthorizationFreezeRecord.status == "frozen",
        )
    )
    if existing_freeze_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该授权已存在冻结权益记录",
        )

    freeze = AuthorizationFreezeRecord(
        authorization_id=auth.id,
        agent_id=user.created_by_agent_id,
        user_id=user.id,
        project_id=auth.game_project_id,
        freeze_type="agent_suspend" if agent is not None else "admin_suspend",
        status="frozen",
        frozen_at=now,
        frozen_by_agent_id=agent.id if agent else None,
        frozen_by_admin_id=admin.id if admin else None,
        original_valid_until=auth.valid_until,
        remaining_hours=remaining_hours,
        estimated_remaining_points=estimated_points,
        remark="停用授权时冻结剩余权益，不返点",
    )
    db.add(freeze)

    auth.status = "suspended"
    await db.flush()

    return _authorization_to_response(auth=auth, project=project)


async def enable_authorization_with_release(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """启用 frozen 授权并释放剩余权益；不扣点、不改钱包、不写账本。"""
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
    )
    project = await _get_project_or_404(auth.game_project_id, db)

    if auth.status != "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有 suspended 授权可以启用",
        )

    freeze_result = await db.execute(
        select(AuthorizationFreezeRecord)
        .where(
            AuthorizationFreezeRecord.authorization_id == auth.id,
            AuthorizationFreezeRecord.status == "frozen",
        )
        .order_by(AuthorizationFreezeRecord.frozen_at.desc())
    )
    freeze = freeze_result.scalars().first()
    if not freeze:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到可释放的冻结权益记录",
        )

    if agent is not None:
        await _assert_agent_project_auth_valid(
            db=db,
            agent=agent,
            project_id=project.id,
            project_name=project.display_name,
        )

    now = datetime.now(timezone.utc)
    if freeze.remaining_hours is None:
        new_valid_until = freeze.original_valid_until
    else:
        new_valid_until = now + timedelta(hours=int(freeze.remaining_hours))

    auth.status = "active"
    auth.valid_until = new_valid_until

    freeze.status = "released"
    freeze.released_at = now
    freeze.released_by_agent_id = agent.id if agent else None
    freeze.released_by_admin_id = admin.id if admin else None
    freeze.new_valid_until = new_valid_until

    await db.flush()

    return _authorization_to_response(auth=auth, project=project)


async def settle_authorization_freezes_on_user_delete(
    user_id: int,
    db: AsyncSession,
    admin: Admin | None,
    settled_at: datetime | None = None,
) -> None:
    """管理员删除用户时把仍 frozen 的权益记录标记为 refunded。"""
    now = settled_at or datetime.now(timezone.utc)
    result = await db.execute(
        select(AuthorizationFreezeRecord).where(
            AuthorizationFreezeRecord.user_id == user_id,
            AuthorizationFreezeRecord.status == "frozen",
        )
    )
    for freeze in result.scalars().all():
        freeze.status = "refunded"
        freeze.refunded_at = now
        freeze.settled_by_admin_id = admin.id if admin else None


def _empty_wallet_preview_snapshot() -> dict:
    return {
        "charged_balance": None,
        "credit_balance": None,
        "frozen_credit": None,
        "available_total": None,
        "enough_balance": None,
        "charged_consumed": None,
        "credit_consumed": None,
        "charged_balance_after": None,
        "credit_balance_after": None,
        "available_total_after": None,
    }


def _build_wallet_preview_snapshot(wallet: AccountingWallet | None, total_cost: float) -> dict:
    charged = float(wallet.charged_balance or 0) if wallet else 0.0
    credit = float(wallet.credit_balance or 0) if wallet else 0.0
    frozen = float(wallet.frozen_credit or 0) if wallet else 0.0
    safe_cost = max(0.0, float(total_cost or 0.0))
    available = charged + max(0.0, credit - frozen)

    charged_consumed = min(charged, safe_cost)
    credit_consumed = max(0.0, safe_cost - charged_consumed)
    charged_after = max(0.0, charged - charged_consumed)
    credit_after = max(0.0, credit - credit_consumed)
    available_after = charged_after + max(0.0, credit_after - frozen)

    return {
        "charged_balance": charged,
        "credit_balance": credit,
        "frozen_credit": frozen,
        "available_total": available,
        "enough_balance": available >= safe_cost,
        "charged_consumed": charged_consumed,
        "credit_consumed": credit_consumed,
        "charged_balance_after": charged_after,
        "credit_balance_after": credit_after,
        "available_total_after": available_after,
    }


async def _build_agent_wallet_preview_snapshot(
    *,
    db: AsyncSession,
    agent_id: int,
    total_cost: float,
) -> dict:
    wallet_result = await db.execute(
        select(AccountingWallet).where(AccountingWallet.agent_id == agent_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    return _build_wallet_preview_snapshot(wallet, total_cost)


async def preview_authorization_renew(
    user_id: int,
    auth_id: int,
    body: AuthorizationRenewRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationRenewPreviewResponse:
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)
    start_at = await _validate_authorization_renew(
        auth=auth,
        project=project,
        new_valid_until=body.valid_until,
        db=db,
        agent=agent,
    )

    cost = await calculate_authorization_cost(
        project_id=project.id,
        user_level=auth.user_level,
        authorized_devices=auth.authorized_devices,
        start_at=start_at,
        valid_until=body.valid_until,
        db=db,
    )

    wallet_snapshot = _empty_wallet_preview_snapshot()
    if agent is not None:
        wallet_snapshot = await _build_agent_wallet_preview_snapshot(
            db=db,
            agent_id=agent.id,
            total_cost=float(cost["total_cost"]),
        )

    return AuthorizationRenewPreviewResponse(
        authorization_id=auth.id,
        game_project_id=project.id,
        game_project_code=project.code_name,
        game_project_name=project.display_name,
        user_level=auth.user_level,
        authorized_devices=int(auth.authorized_devices or 0),
        old_valid_until=auth.valid_until,
        new_valid_until=body.valid_until,
        unit_price=float(cost["unit_price"]),
        period_count=int(cost["period_count"]),
        billing_period=cost["billing_period"],
        billing_period_name=cost["billing_period_name"],
        billing_period_hours=int(cost["billing_period_hours"]),
        paid_hours=int(cost["paid_hours"]),
        unit_label=cost["unit_label"],
        total_cost=float(cost["total_cost"]),
        will_charge=agent is not None,
        agent_id=agent.id if agent else None,
        **wallet_snapshot,
    )


async def renew_authorization(
    user_id: int,
    auth_id: int,
    body: AuthorizationRenewRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationRenewResponse:
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)
    start_at = await _validate_authorization_renew(
        auth=auth,
        project=project,
        new_valid_until=body.valid_until,
        db=db,
        agent=agent,
    )

    old_valid_until = auth.valid_until
    consumed_points = 0.0
    if agent is not None:
        cost = await calculate_authorization_cost(
            project_id=project.id,
            user_level=auth.user_level,
            authorized_devices=auth.authorized_devices,
            start_at=start_at,
            valid_until=body.valid_until,
            db=db,
        )
        consumed_points = float(cost["total_cost"])
        await consume_agent_authorization_points(
            agent_id=agent.id,
            user_id=user.id,
            project_id=project.id,
            authorization_id=auth.id,
            user_level=auth.user_level,
            authorized_devices=auth.authorized_devices,
            start_at=start_at,
            valid_until=body.valid_until,
            db=db,
        )

    auth.valid_until = body.valid_until
    await db.flush()

    return AuthorizationRenewResponse(
        authorization=_authorization_to_response(auth, project, consumed_points),
        consumed_points=consumed_points,
        old_valid_until=old_valid_until,
        new_valid_until=body.valid_until,
    )


async def _validate_authorization_renew(
    auth: Authorization,
    project: GameProject,
    new_valid_until: datetime,
    db: AsyncSession,
    agent: Agent | None,
) -> datetime:
    if auth.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有 active 授权可以续费",
        )
    if int(auth.authorized_devices or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="续费授权设备数必须大于 0",
        )

    now = datetime.now(timezone.utc)
    target = _ensure_aware(new_valid_until)
    base = max(now, _ensure_aware(auth.valid_until)) if auth.valid_until else now
    if target <= base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="续费后的到期时间必须晚于当前有效期",
        )

    if agent is not None:
        await _assert_agent_project_auth_valid(
            db=db,
            agent=agent,
            project_id=project.id,
            project_name=project.display_name,
        )

    return base


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

    # 代理升级前必须复核代理仍拥有该项目授权且未过期
    if agent is not None:
        await _assert_agent_project_auth_valid(
            db=db, agent=agent, project_id=project.id,
            project_name=project.display_name,
        )

    old_devices = int(auth.authorized_devices or 0)
    new_devices = old_devices + additional_devices
    now = datetime.now(timezone.utc)

    if auth.valid_until and _ensure_aware(auth.valid_until) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权已到期，请重新授权")

    level_rule = BILLING_RULES.get(auth.user_level, {})
    period_hours = int(level_rule.get("period_hours", 720))
    valid_until_for_cost = auth.valid_until
    consumed_points = 0.0
    unit_price = 0.0
    new_devices_cost: float | None = None
    old_devices_topup_cost: float | None = None
    old_remaining_hours: int | None = None
    topup_delta_hours: int | None = None

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

    elif mode == "topup_align":
        valid_until_for_cost = now + timedelta(hours=period_hours)
        old_remaining_hours = _ceil_hours(now, auth.valid_until) if auth.valid_until else 0
        topup_delta_hours = max(0, period_hours - old_remaining_hours)

        if agent is not None:
            new_cost = await calculate_authorization_cost(
                project_id=project.id,
                user_level=auth.user_level,
                authorized_devices=additional_devices,
                start_at=now,
                valid_until=valid_until_for_cost,
                db=db,
            )
            new_devices_cost = float(new_cost.get("total_cost") or 0.0)
            unit_price = float(new_cost.get("unit_price") or 0.0)
            period_hours = int(new_cost.get("billing_period_hours") or period_hours)

            topup_cost_dec = Decimal("0.00")
            if old_devices > 0 and topup_delta_hours > 0:
                raw_topup = (
                    Decimal(str(old_devices))
                    * Decimal(str(unit_price))
                    * Decimal(str(topup_delta_hours))
                    / Decimal(str(period_hours))
                )
                topup_cost_dec = raw_topup.quantize(Decimal("0.01"), rounding=ROUND_UP)

            old_devices_topup_cost = float(topup_cost_dec)
            consumed_points = float(Decimal(str(new_devices_cost)) + topup_cost_dec)
        else:
            new_devices_cost = 0.0
            old_devices_topup_cost = 0.0

    else:
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

    wallet_snapshot = _empty_wallet_preview_snapshot()
    if agent is not None:
        wallet_snapshot = await _build_agent_wallet_preview_snapshot(
            db=db,
            agent_id=agent.id,
            total_cost=consumed_points,
        )

    return AuthorizationUpgradePreviewResponse(
        old_devices=old_devices,
        new_devices=new_devices,
        additional_devices=additional_devices,
        mode=mode,
        consumed_points=consumed_points,
        total_cost=consumed_points,
        new_expiry=valid_until_for_cost,
        unit_price=unit_price,
        period_hours=period_hours,
        new_devices_cost=new_devices_cost,
        old_devices_topup_cost=old_devices_topup_cost,
        old_remaining_hours=old_remaining_hours,
        topup_delta_hours=topup_delta_hours,
        **wallet_snapshot,
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

    # 代理升级前必须复核代理仍拥有该项目授权且未过期
    if agent is not None:
        await _assert_agent_project_auth_valid(
            db=db, agent=agent, project_id=project.id,
            project_name=project.display_name,
        )

    old_devices = int(auth.authorized_devices or 0)
    new_devices = old_devices + body.additional_devices
    now = datetime.now(timezone.utc)

    # 检查到期
    if auth.valid_until and _ensure_aware(auth.valid_until) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="授权已到期，请重新授权")

    consumed_points = 0.0
    new_devices_cost: float | None = None
    old_devices_topup_cost: float | None = None
    old_remaining_hours: int | None = None
    topup_delta_hours: int | None = None

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
    elif body.mode == "topup_align":
        period_hours = int(BILLING_RULES.get(auth.user_level, {}).get("period_hours", 720))
        target_valid_until = now + timedelta(hours=period_hours)
        old_remaining = _ceil_hours(now, auth.valid_until) if auth.valid_until else 0
        delta_hours = max(0, period_hours - old_remaining)
        auth.valid_until = target_valid_until

        old_remaining_hours = old_remaining
        topup_delta_hours = delta_hours

        if agent is not None:
            new_cost = await calculate_authorization_cost(
                project_id=project.id,
                user_level=auth.user_level,
                authorized_devices=body.additional_devices,
                start_at=now,
                valid_until=target_valid_until,
                db=db,
            )
            new_devices_cost = float(new_cost.get("total_cost") or 0.0)
            unit_price = float(new_cost.get("unit_price") or 0.0)
            period_hours = int(new_cost.get("billing_period_hours") or period_hours)
            billing_period = str(new_cost.get("billing_period") or BILLING_RULES.get(auth.user_level, {}).get("period", "month"))

            await consume_agent_authorization_points(
                agent_id=agent.id,
                user_id=user.id,
                project_id=project.id,
                authorization_id=auth.id,
                user_level=auth.user_level,
                authorized_devices=body.additional_devices,
                start_at=now,
                valid_until=target_valid_until,
                db=db,
            )

            topup_cost_dec = Decimal("0.00")
            if old_devices > 0 and delta_hours > 0:
                raw_topup = (
                    Decimal(str(old_devices))
                    * Decimal(str(unit_price))
                    * Decimal(str(delta_hours))
                    / Decimal(str(period_hours))
                )
                topup_cost_dec = raw_topup.quantize(Decimal("0.01"), rounding=ROUND_UP)

                await consume_agent_authorization_topup_points(
                    agent_id=agent.id,
                    user_id=user.id,
                    project_id=project.id,
                    authorization_id=auth.id,
                    user_level=auth.user_level,
                    authorized_devices=old_devices,
                    unit_price=unit_price,
                    billing_period=billing_period,
                    billing_period_hours=period_hours,
                    paid_hours=delta_hours,
                    total_cost=float(topup_cost_dec),
                    start_at=now,
                    valid_until=target_valid_until,
                    db=db,
                )

            old_devices_topup_cost = float(topup_cost_dec)
            consumed_points = float(Decimal(str(new_devices_cost)) + topup_cost_dec)
        else:
            new_devices_cost = 0.0
            old_devices_topup_cost = 0.0
    else:
        # 追加模式：到期不变
        if agent is not None and auth.valid_until:
            # 按剩余比例计算
            remaining = _ceil_hours(now, auth.valid_until)
            level_rule = BILLING_RULES.get(auth.user_level, {})
            period_hours = level_rule.get("period_hours", 720)
            periods = max(1, (remaining + period_hours - 1) // period_hours)
            # 取单价
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
        new_devices_cost=new_devices_cost,
        old_devices_topup_cost=old_devices_topup_cost,
        old_remaining_hours=old_remaining_hours,
        topup_delta_hours=topup_delta_hours,
    )


# ═══════════════════════════════════════════════════════════════
# 授权等级升级
# ═══════════════════════════════════════════════════════════════

async def preview_authorization_level_upgrade(
    user_id: int,
    auth_id: int,
    body: AuthorizationLevelUpgradeRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationLevelUpgradePreviewResponse:
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)
    old_cost, new_cost, difference = await _calculate_level_upgrade_difference(
        auth=auth,
        project=project,
        new_user_level=body.user_level,
        db=db,
        admin=admin,
        agent=agent,
    )

    wallet_snapshot = _empty_wallet_preview_snapshot()
    if agent is not None:
        wallet_snapshot = await _build_agent_wallet_preview_snapshot(
            db=db,
            agent_id=agent.id,
            total_cost=difference,
        )

    return AuthorizationLevelUpgradePreviewResponse(
        authorization_id=auth.id,
        game_project_id=project.id,
        game_project_code=project.code_name,
        game_project_name=project.display_name,
        old_user_level=auth.user_level,
        new_user_level=body.user_level,
        old_user_level_name=LEVEL_NAMES.get(auth.user_level, auth.user_level),
        new_user_level_name=LEVEL_NAMES.get(body.user_level, body.user_level),
        authorized_devices=int(auth.authorized_devices or 0),
        valid_until=auth.valid_until,
        old_total_cost=old_cost,
        new_total_cost=new_cost,
        difference_cost=difference,
        will_charge=agent is not None,
        agent_id=agent.id if agent else None,
        **wallet_snapshot,
    )


async def level_upgrade_authorization(
    user_id: int,
    auth_id: int,
    body: AuthorizationLevelUpgradeRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationLevelUpgradeResponse:
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)
    _old_cost, _new_cost, difference = await _calculate_level_upgrade_difference(
        auth=auth,
        project=project,
        new_user_level=body.user_level,
        db=db,
        admin=admin,
        agent=agent,
    )

    old_user_level = auth.user_level
    consumed_points = 0.0
    if agent is not None and difference > 0:
        consumed_points = difference
        await consume_agent_authorization_level_upgrade_diff_points(
            agent_id=agent.id,
            user_id=user.id,
            project_id=project.id,
            authorization_id=auth.id,
            new_user_level=body.user_level,
            authorized_devices=auth.authorized_devices,
            start_at=datetime.now(timezone.utc),
            valid_until=auth.valid_until,
            total_cost=difference,
            db=db,
        )

    auth.user_level = body.user_level
    await db.flush()

    return AuthorizationLevelUpgradeResponse(
        authorization=_authorization_to_response(auth, project, consumed_points),
        consumed_points=consumed_points,
        old_user_level=old_user_level,
        new_user_level=body.user_level,
    )


async def _calculate_level_upgrade_difference(
    auth: Authorization,
    project: GameProject,
    new_user_level: str,
    db: AsyncSession,
    admin: Admin | None,
    agent: Agent | None,
) -> tuple[float, float, float]:
    if auth.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有 active 授权可以升级等级",
        )
    if new_user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别授权只有管理员可以设置",
        )
    if new_user_level == auth.user_level:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新等级不能与当前等级相同",
        )
    if int(auth.authorized_devices or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="升级等级的授权设备数必须大于 0",
        )

    now = datetime.now(timezone.utc)
    if not auth.valid_until:
        if agent is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理等级升级必须存在授权到期时间",
            )
        return 0.0, 0.0, 0.0

    if _ensure_aware(auth.valid_until) <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="授权已到期，请重新授权",
        )

    if agent is not None:
        await _assert_agent_project_auth_valid(
            db=db,
            agent=agent,
            project_id=project.id,
            project_name=project.display_name,
        )

    old_cost = await calculate_authorization_cost(
        project_id=project.id,
        user_level=auth.user_level,
        authorized_devices=auth.authorized_devices,
        start_at=now,
        valid_until=auth.valid_until,
        db=db,
    )
    new_cost = await calculate_authorization_cost(
        project_id=project.id,
        user_level=new_user_level,
        authorized_devices=auth.authorized_devices,
        start_at=now,
        valid_until=auth.valid_until,
        db=db,
    )
    old_total = float(old_cost["total_cost"])
    new_total = float(new_cost["total_cost"])
    return old_total, new_total, max(new_total - old_total, 0.0)


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
        "hierarchy_depth": agent.hierarchy_depth,
        "status": agent.status,
        "commission_rate": float(agent.commission_rate) if agent.commission_rate is not None else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "authorized_projects": authorized_projects,
        "balance": {
            "charged_balance": float(wallet.charged_balance) if wallet else 0.0,
            "credit_balance": float(wallet.credit_balance) if wallet else 0.0,
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


async def _assert_agent_project_auth_valid(
    *,
    db: AsyncSession,
    agent: Agent,
    project_id: int,
    project_name: str = "",
) -> None:
    """
    校验代理当前仍拥有指定项目的有效授权（status=active 且未过期）。
    用于用户授权、升级、续费等需要代理项目准入的操作前置校验。
    """
    result = await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent.id,
            AgentProjectAuth.project_id == project_id,
            AgentProjectAuth.status == "active",
        )
    )
    auth_record = result.scalar_one_or_none()
    if not auth_record:
        name = project_name or f"项目 {project_id}"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"代理没有项目「{name}」的授权权限",
        )
    if auth_record.valid_until is not None and _ensure_aware(auth_record.valid_until) <= datetime.now(timezone.utc):
        name = project_name or f"项目 {project_id}"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"代理的项目「{name}」授权已过期",
        )


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


def _authorization_remaining_hours(auth: Authorization, now: datetime) -> int | None:
    if auth.valid_until is None:
        return None

    valid_until = _ensure_aware(auth.valid_until)
    if valid_until <= now:
        return 0

    seconds = (valid_until - now).total_seconds()
    return int((seconds + 3599) // 3600)


async def _estimate_authorization_remaining_points(
    *,
    auth: Authorization,
    remaining_hours: int | None,
    db: AsyncSession,
) -> float:
    if remaining_hours is None or remaining_hours <= 0:
        return 0.0

    result = await db.execute(
        select(AuthorizationChargeSnapshot)
        .where(AuthorizationChargeSnapshot.authorization_id == auth.id)
        .order_by(AuthorizationChargeSnapshot.created_at.desc())
    )
    snapshot = result.scalars().first()
    if not snapshot:
        return 0.0

    paid_hours = int(snapshot.paid_hours or 0)
    if paid_hours <= 0:
        return 0.0

    original_cost = float(snapshot.original_cost or 0.0)
    estimate = original_cost * min(remaining_hours, paid_hours) / paid_hours
    return round(max(0.0, estimate), 2)
