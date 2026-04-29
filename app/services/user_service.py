r"""
文件位置: app/services/user_service.py
文件名称: user_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    用户管理服务层，包含全部业务逻辑：
      - create_user()           创建用户（管理员或代理调用）
      - list_users()            查询用户列表（按调用方权限过滤）
      - get_user()              查询用户详情（含授权列表）
      - update_user()           更新用户状态/级别/到期时间
      - grant_authorization()   为用户授予游戏授权
      - revoke_authorization()  撤销游戏授权

    权限规则：
      - 管理员：可创建所有级别用户（含 tester），可查看所有用户
      - 代理：不能创建 tester 级别，只能查看自己直接创建的用户
      - tester 级别由数据库 CHECK 约束 + 应用层双重保护

    TODO(P1): 代理权限范围扩展为递归子树查询（WITH RECURSIVE）

关联文档:
    [[01-网络验证系统/架构设计]] 4. 功能模块清单
    [[01-网络验证系统/数据库设计]] 2.3 用户表

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.main.models import Admin, Agent, AgentProjectAuth, Authorization, DeviceBinding, GameProject, User
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationInfo,
    AuthorizationResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
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

    约束：
      1. tester 级别只有管理员能创建（应用层 + 数据库层双重保护）
      2. 代理创建时检查 max_users 配额（0 表示无限制，跳过检查）
      3. 用户名全局唯一
    """
    if body.user_level == "tester" and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tester 级别用户只有管理员能创建",
        )

    if agent is not None and agent.max_users != 0:
        count_result = await db.execute(
            select(func.count(User.id)).where(
                User.created_by_agent_id == agent.id
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
    await db.flush()    # 获取 user.id，但还未 commit（get_main_db 依赖会在请求结束时统一 commit）

    return _user_to_response(user, authorizations=[])


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
    """
    查询用户列表（分页）。
    管理员可见全部用户；代理只能看自己直接创建的用户。
    Phase 2 将扩展代理权限为递归子树查询。
    """
    query = select(User)

    # 默认排除已删除用户（is_deleted=True）
    # 已删除 ≠ 已停用：停用用户仍在列表中显示（有停用徽章），删除的则完全从列表消失
    query = query.where(User.is_deleted == False)  # noqa: E712

    if agent is not None:
        query = query.where(User.created_by_agent_id == agent.id)

    if status_filter:
        query = query.where(User.status == status_filter)
    if level_filter:
        query = query.where(User.user_level == level_filter)
    if project_id_filter:
        # 只返回有该项目有效授权的用户
        query = query.where(
            User.id.in_(
                select(Authorization.user_id).where(
                    Authorization.game_project_id == project_id_filter,
                    Authorization.status == "active",
                )
            )
        )

    # 计算总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # 分页查询
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(User.id.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()

    if not users:
        return UserListResponse(users=[], total=total, page=page, page_size=page_size)

    user_ids = [u.id for u in users]

    # 授权总数（含 suspended）
    auth_total_result = await db.execute(
        select(Authorization.user_id, func.count(Authorization.id).label("cnt"))
        .where(Authorization.user_id.in_(user_ids))
        .group_by(Authorization.user_id)
    )
    auth_total_map = {row.user_id: row.cnt for row in auth_total_result.all()}

    # 有效授权数（status = active）
    active_auth_result = await db.execute(
        select(Authorization.user_id, func.count(Authorization.id).label("cnt"))
        .where(Authorization.user_id.in_(user_ids), Authorization.status == "active")
        .group_by(Authorization.user_id)
    )
    auth_active_map = {row.user_id: row.cnt for row in active_auth_result.all()}

    # 设备绑定计数
    device_counts_result = await db.execute(
        select(DeviceBinding.user_id, func.count(DeviceBinding.id).label("cnt"))
        .where(
            DeviceBinding.user_id.in_(user_ids),
            DeviceBinding.status == "active",   # 模型一律用 active
        )
        .group_by(DeviceBinding.user_id)
    )
    device_map = {row.user_id: row.cnt for row in device_counts_result.all()}

    # 有效授权项目名称（一次查询）
    active_proj_result = await db.execute(
        select(Authorization.user_id, GameProject.display_name)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(
            Authorization.user_id.in_(user_ids),
            Authorization.status == "active",
        )
        .order_by(GameProject.display_name)
    )
    proj_names_map: dict[int, list[str]] = {}
    for uid, name in active_proj_result.all():
        proj_names_map.setdefault(uid, []).append(name)

    return UserListResponse(
        users=[
            _user_to_response(
                u,
                authorizations=[],
                authorization_count=auth_total_map.get(u.id, 0),
                active_authorization_count=auth_active_map.get(u.id, 0),
                active_project_names=proj_names_map.get(u.id, []),
                device_binding_count=device_map.get(u.id, 0),
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_user(user_id: int, db: AsyncSession) -> UserResponse:
    """
    查询用户详情，包含当前所有授权记录。
    使用单次联表查询加载授权 + 游戏项目信息，避免 N+1。
    """
    user = await _get_user_or_404(user_id, db)

    # 联表查询：一次性加载该用户所有授权及对应游戏项目信息
    auth_result = await db.execute(
        select(Authorization, GameProject)
        .join(GameProject, Authorization.game_project_id == GameProject.id)
        .where(Authorization.user_id == user_id)
        .order_by(Authorization.id)
    )
    rows = auth_result.all()

    authorizations = [
        AuthorizationInfo(
            id=auth.id,
            game_project_id=auth.game_project_id,
            game_project_code=project.code_name,
            game_project_name=project.display_name,
            valid_from=auth.valid_from,
            valid_until=auth.valid_until,
            status=auth.status,
        )
        for auth, project in rows
    ]

    return _user_to_response(user, authorizations=authorizations)


async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: AsyncSession,
) -> UserResponse:
    """
    更新用户属性：状态、级别、到期时间。
    只更新请求体中非 None 的字段。
    """
    user = await _get_user_or_404(user_id, db)

    if body.status is not None:
        user.status = body.status
    if body.user_level is not None:
        user.user_level = body.user_level
    if body.max_devices is not None:
        user.max_devices = body.max_devices
    if "expired_at" in body.model_fields_set:
        # 明确传入 expired_at（含 None，用于设置永久有效）
        user.expired_at = body.expired_at

    await db.flush()
    await db.refresh(user)  # 重新加载 updated_at 等 onupdate 字段，防止 MissingGreenlet
    return _user_to_response(user, authorizations=[])


async def grant_authorization(
    user_id: int,
    body: AuthorizationCreateRequest,
    db: AsyncSession,
    admin: Admin | None = None,
    agent: Agent | None = None,
) -> AuthorizationResponse:
    """
    为用户授予指定项目的访问权限。

    权限规则：
      - 管理员：可授权任意项目
      - 代理：只能授权自己已有效项目授权的项目

    如已有授权记录（含已 suspended），则恢复并更新到期时间。
    """
    user = await _get_user_or_404(user_id, db)
    project = await _get_project_or_404(body.game_project_id, db)

    # 代理权限检查：只能授权自己已有的项目
    if agent is not None:
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

    # 检查是否已有授权记录
    existing_result = await db.execute(
        select(Authorization).where(
            Authorization.user_id == user_id,
            Authorization.game_project_id == body.game_project_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

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
    )


async def revoke_authorization(
    user_id: int,
    auth_id: int,
    db: AsyncSession,
) -> None:
    """
    撤销用户的游戏授权。
    状态改为 suspended，不物理删除（保留历史记录）。
    """
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
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_user_or_404(user_id: int, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
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
            GameProject.is_active == True,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"游戏项目 ID={project_id} 不存在或已下线",
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
) -> UserResponse:
    """将 User ORM 对象转换为 UserResponse Pydantic 模型。"""
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
        authorizations=authorizations,
        authorization_count=authorization_count,
        active_authorization_count=active_authorization_count,
        active_project_names=active_project_names or [],
        device_binding_count=device_binding_count,
    )
