r"""
文件位置: app/services/user_service.py
文件名称: user_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.2.0
功能说明:
    用户管理服务层。

核心口径:
    - 用户 User 是账号主体。
    - 用户等级、授权设备数、到期时间不再以 User 为主口径。
    - 项目内等级、项目授权设备数、项目到期时间统一归属 Authorization。
    - 一个用户可以在 A 项目是普通，在 B 项目是 VIP。
    - 一个用户可以在不同项目拥有不同授权设备数和不同到期时间。

本版增强:
    - 用户列表返回创建者信息。
    - 用户列表/详情返回项目授权明细。
    - 项目筛选时，只返回对应项目的授权明细。
    - 授权明细按项目分开显示：等级、授权设备、已激活、未激活、到期时间。
    - 支持修改/重置密码。
    - 代理授权项目时按 Authorization 维度扣点。
    - 新增创建者代理详情聚合能力。

安全边界:
    - 不查询旧密码明文。
    - 管理员自动生成密码时，只在响应中一次性返回新密码。
    - 代理不能自动生成并查看明文，只能手动修改密码。
"""

import secrets
import string
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.main.models import (
    Admin,
    Agent,
    AgentBalance,
    AgentProjectAuth,
    Authorization,
    GameProject,
    LoginLog,
    User,
)
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationInfo,
    AuthorizationResponse,
    AuthorizationUpdateRequest,
    CreatorAgentDetailResponse,
    UserCreateRequest,
    UserListResponse,
    UserPasswordUpdateRequest,
    UserPasswordUpdateResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.balance_service import (
    LEVEL_NAMES,
    consume_agent_authorization_points,
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
      - 项目等级、设备数、到期时间在项目授权时设置。
      - User.user_level / User.max_devices / User.expired_at 仅保留兼容字段。
    """
    if body.user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别用户只有管理员能创建",
        )

    if agent is not None and agent.max_users != 0:
        count_result = await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == agent.id,
                User.is_deleted == False,  # noqa: E712
            )
        )
        current_count = count_result.scalar_one()
        if current_count >= agent.max_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"已达到代理用户配额上限（{agent.max_users} 人）",
            )

    await _assert_username_unique(body.username, db)

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),

        # 兼容旧字段，新页面不再主展示
        user_level=body.user_level,
        max_devices=body.max_devices,
        expired_at=body.expired_at,

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
      - status：过滤 User.status
      - level：过滤 Authorization.user_level
      - project_id：过滤 Authorization.game_project_id
      - creator_agent_id：管理员查看指定代理创建的用户
    """
    query = select(User).where(User.is_deleted == False)  # noqa: E712

    if agent is not None:
        query = query.where(User.created_by_agent_id == agent.id)

    if admin is not None and creator_agent_id_filter:
        query = query.where(User.created_by_agent_id == creator_agent_id_filter)

    if status_filter:
        query = query.where(User.status == status_filter)

    # 用户等级现在归属项目授权，因此 level 过滤走 Authorization.user_level
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
        return UserListResponse(users=[], total=total, page=page, page_size=page_size)

    creator_agent_map = await _load_creator_agent_map(users, db)

    # 项目筛选时，授权明细只返回对应项目；否则返回全部 active 授权
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
    auth_total_map = {row.user_id: row.cnt for row in auth_total_result.all()}

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
            a for a in authorizations
            if a.status == "active" and not a.is_expired
        ]),
        active_project_names=[
            a.game_project_name
            for a in authorizations
            if a.status == "active" and not a.is_expired
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

    # 兼容旧字段：新页面不再主使用
    if body.user_level is not None:
        if body.user_level == "tester" and admin is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="tester 级别只有管理员能设置",
            )
        user.user_level = body.user_level

    if body.max_devices is not None:
        user.max_devices = body.max_devices

    if "expired_at" in body.model_fields_set:
        user.expired_at = body.expired_at

    await db.flush()
    await db.refresh(user)

    return await get_user(user_id=user_id, db=db, admin=admin, agent=agent)


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

        agent_project_auth = await db.execute(
            select(AgentProjectAuth).where(
                AgentProjectAuth.agent_id == agent.id,
                AgentProjectAuth.project_id == body.game_project_id,
                AgentProjectAuth.status == "active",
            )
        )
        if not agent_project_auth.scalar_one_or_none():
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

    consumed_points = 0.0

    if agent is not None:
        now = datetime.now(timezone.utc)
        consumed_points = await consume_agent_authorization_points(
            agent_id=agent.id,
            user_id=user.id,
            project_id=project.id,
            user_level=body.user_level,
            authorized_devices=body.authorized_devices,
            start_at=now,
            valid_until=body.valid_until,
            db=db,
        )

    if existing:
        existing.status = "active"
        existing.user_level = body.user_level
        existing.authorized_devices = body.authorized_devices
        existing.valid_until = body.valid_until
        auth = existing
    else:
        auth = Authorization(
            user_id=user_id,
            game_project_id=body.game_project_id,
            user_level=body.user_level,
            authorized_devices=body.authorized_devices,
            valid_until=body.valid_until,
            status="active",
        )
        db.add(auth)

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
    """
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理暂不能直接修改已授权项目，请由管理员处理",
        )

    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    project = await _get_project_or_404(auth.game_project_id, db)

    if body.user_level is not None:
        auth.user_level = body.user_level

    if body.authorized_devices is not None:
        auth.authorized_devices = body.authorized_devices

    if "valid_until" in body.model_fields_set:
        auth.valid_until = body.valid_until

    if body.status is not None:
        auth.status = body.status

    await db.flush()

    return _authorization_to_response(
        auth=auth,
        project=project,
        consumed_points=0.0,
    )


async def revoke_authorization(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> None:
    """撤销授权。当前规则：不退款。"""
    user = await _get_user_or_404(user_id, db)
    _assert_can_access_user(user=user, admin=admin, agent=agent)

    auth = await _get_authorization_or_404(user_id=user_id, auth_id=auth_id, db=db)
    auth.status = "suspended"
    await db.flush()


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
        select(AgentBalance).where(AgentBalance.agent_id == agent_id)
    )
    balance = balance_result.scalar_one_or_none()

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
        "level": agent.level,
        "status": agent.status,
        "max_users": agent.max_users,
        "commission_rate": float(agent.commission_rate) if agent.commission_rate is not None else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "authorized_projects": authorized_projects,
        "balance": {
            "charged_points": float(balance.charged_points) if balance else 0.0,
            "credit_points": float(balance.credit_points) if balance else 0.0,
            "frozen_credit": float(balance.frozen_credit) if balance else 0.0,
            "available_total": (
                float(balance.charged_points)
                + float(balance.credit_points)
                - float(balance.frozen_credit)
            ) if balance else 0.0,
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


async def _get_project_or_404(project_id: int, db: AsyncSession) -> GameProject:
    result = await db.execute(
        select(GameProject).where(
            GameProject.id == project_id,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID={project_id} 不存在或已下线",
        )

    return project


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

        # 兼容旧字段
        user_level=user.user_level,
        max_devices=user.max_devices,
        expired_at=user.expired_at,

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


async def _load_creator_agent_map(users: list[User], db: AsyncSession) -> dict[int, str]:
    agent_ids = sorted({u.created_by_agent_id for u in users if u.created_by_agent_id})
    if not agent_ids:
        return {}

    result = await db.execute(
        select(Agent.id, Agent.username).where(Agent.id.in_(agent_ids))
    )
    return {row.id: row.username for row in result.all()}


async def _load_project_activation_count_map(
    user_ids: list[int],
    db: AsyncSession,
) -> dict[tuple[int, int], int]:
    """
    统计每个用户在每个项目成功登录激活过的去重设备数。

    注意:
        当前 device_binding 表没有 project_id 字段，因此这里使用 LoginLog:
        user_id + game_project_id + distinct device_fingerprint + success=true
    """
    result = await db.execute(
        select(
            LoginLog.user_id,
            LoginLog.game_project_id,
            func.count(func.distinct(LoginLog.device_fingerprint)).label("cnt"),
        )
        .where(
            LoginLog.user_id.in_(user_ids),
            LoginLog.success == True,  # noqa: E712
            LoginLog.device_fingerprint.is_not(None),
            LoginLog.game_project_id.is_not(None),
        )
        .group_by(LoginLog.user_id, LoginLog.game_project_id)
    )

    return {
        (row.user_id, row.game_project_id): row.cnt
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

    user_ids = [u.id for u in users]

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
        authorized_devices = auth.authorized_devices
        activated_devices = activation_map.get((auth.user_id, auth.game_project_id), 0)

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


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))