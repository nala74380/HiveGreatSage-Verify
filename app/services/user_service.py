r"""
文件位置: app/services/user_service.py
文件名称: user_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    用户管理服务层。

本版增强:
    - 用户列表返回创建者信息
    - 用户列表/详情返回项目授权明细
    - 授权明细按项目分开显示授权设备、已激活设备、未激活设备、到期时间
    - 支持修改/重置密码
    - 代理授权项目时触发点数扣除

安全边界:
    - 不查询旧密码明文。
    - 管理员自动生成密码时，只在响应中一次性返回新密码。
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
    AgentProjectAuth,
    Authorization,
    DeviceBinding,
    GameProject,
    LoginLog,
    User,
)
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationInfo,
    AuthorizationResponse,
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


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def create_user(
    body: UserCreateRequest,
    db: AsyncSession,
    admin: Admin | None,
    agent: Agent | None,
) -> UserResponse:
    """
    创建用户。

    规则:
      - tester 只有管理员能创建。
      - 代理不能创建永久有效用户。
      - 代理不能创建 max_devices=0 的无限制用户。
      - 代理创建用户仍不直接扣点；真正扣点发生在项目授权时。
    """
    if body.user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别用户只有管理员能创建",
        )

    if agent is not None:
        if body.expired_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理创建用户必须设置到期时间",
            )

        if body.max_devices == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理创建用户不允许设置无限设备",
            )

        if agent.max_users != 0:
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
        user_level=body.user_level,
        max_devices=body.max_devices,
        created_by_admin=admin is not None,
        created_by_agent_id=agent.id if agent else None,
        expired_at=body.expired_at,
        status="active",
    )
    db.add(user)
    await db.flush()

    return _user_to_response(
        user,
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
) -> UserListResponse:
    """查询用户列表。"""
    query = select(User).where(User.is_deleted == False)  # noqa: E712

    if agent is not None:
        query = query.where(User.created_by_agent_id == agent.id)

    if status_filter:
        query = query.where(User.status == status_filter)

    if level_filter:
        query = query.where(User.user_level == level_filter)

    if project_id_filter:
        query = query.where(
            User.id.in_(
                select(Authorization.user_id).where(
                    Authorization.game_project_id == project_id_filter,
                    Authorization.status == "active",
                )
            )
        )

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

    user_ids = [u.id for u in users]

    creator_agent_map = await _load_creator_agent_map(users, db)
    device_count_map = await _load_user_device_count_map(user_ids, db)
    auth_details_map = await _load_authorization_details_map(users, only_active=True, db=db)

    auth_total_result = await db.execute(
        select(Authorization.user_id, func.count(Authorization.id).label("cnt"))
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.user_id)
    )
    auth_total_map = {row.user_id: row.cnt for row in auth_total_result.all()}

    active_auth_result = await db.execute(
        select(Authorization.user_id, func.count(Authorization.id).label("cnt"))
        .where(
            Authorization.user_id.in_(user_ids),
            Authorization.status == "active",
        )
        .group_by(Authorization.user_id)
    )
    active_auth_map = {row.user_id: row.cnt for row in active_auth_result.all()}

    return UserListResponse(
        users=[
            _user_to_response(
                u,
                authorizations=auth_details_map.get(u.id, []),
                authorization_count=auth_total_map.get(u.id, 0),
                active_authorization_count=active_auth_map.get(u.id, 0),
                active_project_names=[
                    item.game_project_name
                    for item in auth_details_map.get(u.id, [])
                    if item.status == "active"
                ],
                device_binding_count=device_count_map.get(u.id, 0),
                creator_agent_username=creator_agent_map.get(u.created_by_agent_id),
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_user(user_id: int, db: AsyncSession) -> UserResponse:
    """查询用户详情，包含所有授权记录。"""
    user = await _get_user_or_404(user_id, db)

    creator_agent_username = None
    if user.created_by_agent_id:
        result = await db.execute(
            select(Agent.username).where(Agent.id == user.created_by_agent_id)
        )
        creator_agent_username = result.scalar_one_or_none()

    device_count_map = await _load_user_device_count_map([user.id], db)
    auth_details_map = await _load_authorization_details_map([user], only_active=False, db=db)

    authorizations = auth_details_map.get(user.id, [])

    return _user_to_response(
        user,
        authorizations=authorizations,
        authorization_count=len(authorizations),
        active_authorization_count=len([a for a in authorizations if a.status == "active"]),
        active_project_names=[
            a.game_project_name for a in authorizations if a.status == "active"
        ],
        device_binding_count=device_count_map.get(user.id, 0),
        creator_agent_username=creator_agent_username,
    )


async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: AsyncSession,
) -> UserResponse:
    """更新用户属性。"""
    user = await _get_user_or_404(user_id, db)

    if body.status is not None:
        user.status = body.status

    if body.user_level is not None:
        user.user_level = body.user_level

    if body.max_devices is not None:
        user.max_devices = body.max_devices

    if "expired_at" in body.model_fields_set:
        user.expired_at = body.expired_at

    await db.flush()
    await db.refresh(user)

    return await get_user(user_id=user_id, db=db)


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

    if agent is not None and user.created_by_agent_id != agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="代理只能修改自己创建用户的密码",
        )

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


async def grant_authorization(
    user_id: int,
    body: AuthorizationCreateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """
    为用户授予指定项目权限。

    代理授权规则:
      - 只能授权自己已有权限的项目。
      - 必须设置 valid_until。
      - 用户 max_devices 不能为 0。
      - 授权成功前必须完成扣点。
    """
    user = await _get_user_or_404(user_id, db)
    project = await _get_project_or_404(body.game_project_id, db)

    if agent is not None:
        if user.created_by_agent_id != agent.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="代理只能给自己创建的用户授权项目",
            )

        if body.valid_until is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理授权项目必须设置到期时间，不能永久有效",
            )

        if user.max_devices == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理授权用户的设备数不能为无限制",
            )

        auth_check = await db.execute(
            select(AgentProjectAuth).where(
                AgentProjectAuth.agent_id == agent.id,
                AgentProjectAuth.project_id == body.game_project_id,
                AgentProjectAuth.status == "active",
            )
        )
        if not auth_check.scalar_one_or_none():
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

    consumed_points = 0.0

    if agent is not None:
        now = datetime.now(timezone.utc)

        if existing and existing.status == "active" and existing.valid_until:
            base_from = max(_ensure_aware(existing.valid_until), now)
        else:
            base_from = now

        # 新到期时间不晚于原到期时间，不额外扣点。
        if body.valid_until and _ensure_aware(body.valid_until) > base_from:
            consumed_points = await consume_agent_authorization_points(
                agent_id=agent.id,
                user_id=user.id,
                project_id=project.id,
                user_level=user.user_level,
                device_count=user.max_devices,
                start_at=base_from,
                valid_until=body.valid_until,
                db=db,
            )

    if existing:
        existing.status = "active"
        existing.valid_until = body.valid_until
        await db.flush()
        auth = existing
    else:
        auth = Authorization(
            user_id=user_id,
            game_project_id=body.game_project_id,
            valid_until=body.valid_until,
            status="active",
        )
        db.add(auth)
        await db.flush()

    return AuthorizationResponse(
        id=auth.id,
        user_id=user_id,
        game_project_id=project.id,
        game_project_code=project.code_name,
        game_project_name=project.display_name,
        valid_from=auth.valid_from,
        valid_until=auth.valid_until,
        status=auth.status,
        consumed_points=consumed_points,
    )


async def revoke_authorization(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
) -> None:
    """撤销授权，不退款。"""
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

    auth.status = "suspended"
    await db.flush()


# ─────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────

async def _get_user_or_404(user_id: int, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
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


async def _assert_username_unique(username: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{username}' 已存在",
        )


def _user_to_response(
    user: User,
    authorizations: list[AuthorizationInfo],
    authorization_count: int = 0,
    active_authorization_count: int = 0,
    active_project_names: list[str] | None = None,
    device_binding_count: int = 0,
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
        user_level=user.user_level,
        status=user.status,
        max_devices=user.max_devices,
        created_at=user.created_at,
        updated_at=user.updated_at,
        expired_at=user.expired_at,
        created_by_admin=user.created_by_admin,
        created_by_agent_id=user.created_by_agent_id,
        created_by_type=created_by_type,
        created_by_display=created_by_display,
        created_by_agent_username=creator_agent_username,
        authorizations=authorizations,
        authorization_count=authorization_count,
        active_authorization_count=active_authorization_count,
        active_project_names=active_project_names or [],
        device_binding_count=device_binding_count,
    )


async def _load_creator_agent_map(users: list[User], db: AsyncSession) -> dict[int, str]:
    agent_ids = sorted({u.created_by_agent_id for u in users if u.created_by_agent_id})
    if not agent_ids:
        return {}

    result = await db.execute(
        select(Agent.id, Agent.username).where(Agent.id.in_(agent_ids))
    )
    return {row.id: row.username for row in result.all()}


async def _load_user_device_count_map(user_ids: list[int], db: AsyncSession) -> dict[int, int]:
    result = await db.execute(
        select(DeviceBinding.user_id, func.count(DeviceBinding.id).label("cnt"))
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",
        )
        .group_by(DeviceBinding.user_id)
    )
    return {row.user_id: row.cnt for row in result.all()}


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
) -> dict[int, list[AuthorizationInfo]]:
    if not users:
        return {}

    user_map = {u.id: u for u in users}
    user_ids = list(user_map.keys())

    query = (
        select(Authorization, GameProject)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(Authorization.user_id.in_(user_ids))
        .order_by(Authorization.user_id, GameProject.display_name)
    )

    if only_active:
        query = query.where(Authorization.status == "active")

    activation_map = await _load_project_activation_count_map(user_ids, db)

    result = await db.execute(query)
    rows = result.all()

    data: dict[int, list[AuthorizationInfo]] = {}

    for auth, project in rows:
        user = user_map[auth.user_id]
        authorized_devices = user.max_devices
        activated_devices = activation_map.get((auth.user_id, auth.game_project_id), 0)

        if authorized_devices == 0:
            inactive_devices = None
        else:
            inactive_devices = max(authorized_devices - activated_devices, 0)

        item = AuthorizationInfo(
            id=auth.id,
            game_project_id=auth.game_project_id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            project_type=project.project_type,
            user_level=user.user_level,
            user_level_name=LEVEL_NAMES.get(user.user_level, user.user_level),
            authorized_devices=authorized_devices,
            activated_devices=activated_devices,
            inactive_devices=inactive_devices,
            valid_from=auth.valid_from,
            valid_until=auth.valid_until,
            status=auth.status,
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