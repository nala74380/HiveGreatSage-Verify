r"""
文件位置: app/routers/users.py
文件名称: users.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.3.0
功能说明:
    用户管理路由。

核心口径:
    - User 是账号主体。
    - Authorization 是用户在某项目下的授权记录。
    - 项目内等级、设备数、到期时间全部归属 Authorization。

接口:
      POST   /api/users/
      GET    /api/users/
      GET    /api/users/creators/agents/{agent_id}
      GET    /api/users/{user_id}
      PATCH  /api/users/{user_id}
      DELETE /api/users/{user_id}
      PATCH  /api/users/{user_id}/password
      POST   /api/users/{user_id}/authorizations
      PATCH  /api/users/{user_id}/authorizations/{auth_id}
      DELETE /api/users/{user_id}/authorizations/{auth_id}
      GET    /api/users/{user_id}/authorizations/{auth_id}/upgrade/preview
      POST   /api/users/{user_id}/authorizations/{auth_id}/upgrade

鉴权:
    - Admin Token：操作所有用户。
    - Agent Token：操作自己创建的用户。
    - 创建者详情目前仅 Admin Token 可访问。

改进历史:
    V1.3.0 (2026-05-07): 用户创建、更新、删除、密码重置、授权增改停用升级接入 audit_log。
    V1.2.1 (2026-04-29): 项目授权接口整理。
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis, is_token_revoked
from app.core.security import decode_admin_token, decode_agent_token
from app.database import get_main_db
from app.models.main.models import Admin, Agent
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationCostPreviewResponse,
    AuthorizationRenewPreviewResponse,
    AuthorizationRenewRequest,
    AuthorizationRenewResponse,
    AuthorizationResponse,
    AuthorizationUpdateRequest,
    AuthorizationUpgradePreviewResponse,
    AuthorizationUpgradeRequest,
    AuthorizationUpgradeResponse,
    CreatorAgentDetailResponse,
    UserCreateRequest,
    UserListResponse,
    UserPasswordUpdateRequest,
    UserPasswordUpdateResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.audit_service import create_audit_log
from app.services.user_service import (
    create_user,
    enable_authorization_with_release,
    get_creator_agent_detail,
    get_user,
    grant_authorization,
    list_users,
    preview_authorization_cost,
    preview_authorization_renew,
    preview_authorization_upgrade,
    renew_authorization,
    revoke_authorization,
    suspend_authorization_with_freeze,
    soft_delete_user,
    update_authorization,
    update_user,
    update_user_password,
    upgrade_authorization,
)

router = APIRouter()
_http_bearer = HTTPBearer(auto_error=False)


async def _resolve_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_main_db),
) -> tuple[Admin | None, Agent | None]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要管理员或代理身份才能访问",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 校验 jti 未被吊销（与 dependencies.py get_current_admin/agent 一致）
    async def _check_blacklist(payload: dict) -> None:
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 缺少 jti，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if await is_token_revoked(redis, str(jti)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已被吊销，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        payload = decode_admin_token(token)
        await _check_blacklist(payload)
        admin_id = int(payload["sub"])
        result = await db.execute(select(Admin).where(Admin.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin and admin.status == "active":
            return admin, None
    except JWTError:
        pass

    try:
        payload = decode_agent_token(token)
        await _check_blacklist(payload)
        agent_id = int(payload["sub"])
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent and agent.status == "active":
            return None, agent
    except JWTError:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="需要管理员或代理身份才能访问",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _actor(caller: tuple[Admin | None, Agent | None]) -> tuple[str, int | None]:
    """将调用方转换为 audit_log actor_type / actor_id。"""
    admin, agent = caller
    if admin is not None:
        return "admin", admin.id
    if agent is not None:
        return "agent", agent.id
    return "system", None


def _actor_metadata(caller: tuple[Admin | None, Agent | None]) -> dict:
    """生成调用方审计元数据。"""
    admin, agent = caller
    if admin is not None:
        return {
            "caller_type": "admin",
            "caller_id": admin.id,
            "caller_username": admin.username,
        }
    if agent is not None:
        return {
            "caller_type": "agent",
            "caller_id": agent.id,
            "caller_username": agent.username,
            "caller_hierarchy_depth": agent.hierarchy_depth,
        }
    return {"caller_type": "system"}


def _authorization_metadata(auth: AuthorizationResponse) -> dict:
    """生成项目授权审计元数据。"""
    return {
        "authorization_id": auth.id,
        "user_id": auth.user_id,
        "game_project_id": auth.game_project_id,
        "game_project_name": getattr(auth, "game_project_name", None),
        "user_level": auth.user_level,
        "authorized_devices": auth.authorized_devices,
        "valid_until": auth.valid_until.isoformat() if auth.valid_until else None,
        "status": auth.status,
    }


# ═══════════════════════════════════════════════════════════════
# 用户基础
# ═══════════════════════════════════════════════════════════════

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    body: UserCreateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    admin, agent = caller
    result = await create_user(body=body, db=db, admin=admin, agent=agent)
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user.create",
        target_type="user",
        target_id=result.id,
        summary=f"创建用户 {result.username}",
        metadata={
            **_actor_metadata(caller),
            "user_id": result.id,
            "username": result.username,
            "status": result.status,
            "created_by_admin": result.created_by_admin,
            "created_by_agent_id": result.created_by_agent_id,
        },
    )
    return result


@router.get("/", response_model=UserListResponse)
async def list_users_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    level_filter: str | None = Query(default=None, alias="level"),
    project_id: int | None = Query(default=None, description="按项目过滤"),
    creator_agent_id: int | None = Query(default=None, description="按创建代理过滤，仅管理员使用"),
    creator_agent_tier_level: int | None = Query(default=None, ge=1, le=4, description="按创建代理业务等级过滤，仅管理员使用"),
    creator_agent_can_create_sub_agents: bool | None = Query(default=None, description="按创建代理是否可创建下级过滤，仅管理员使用"),
    creator_agent_risk_status: str | None = Query(default=None, pattern="^(normal|watch|restricted|frozen)$", description="按创建代理风险状态过滤，仅管理员使用"),
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserListResponse:
    admin, agent = caller
    return await list_users(
        db=db,
        admin=admin,
        agent=agent,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        level_filter=level_filter,
        project_id_filter=project_id,
        creator_agent_id_filter=creator_agent_id,
        creator_agent_tier_level_filter=creator_agent_tier_level,
        creator_agent_can_create_sub_agents_filter=creator_agent_can_create_sub_agents,
        creator_agent_risk_status_filter=creator_agent_risk_status,
    )


# 注意：该静态路由必须放在 /{user_id} 动态路由之前。
@router.get(
    "/creators/agents/{agent_id}",
    response_model=CreatorAgentDetailResponse,
)
async def creator_agent_detail_endpoint(
    agent_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> CreatorAgentDetailResponse:
    admin, _agent = caller
    return await get_creator_agent_detail(
        agent_id=agent_id,
        db=db,
        admin=admin,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_endpoint(
    user_id: int,
    project_id: int | None = Query(default=None, description="只返回指定项目授权明细"),
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    admin, agent = caller
    return await get_user(
        user_id=user_id,
        db=db,
        admin=admin,
        agent=agent,
        project_id_filter=project_id,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: int,
    body: UserUpdateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    admin, agent = caller
    result = await update_user(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user.update",
        target_type="user",
        target_id=result.id,
        summary=f"更新用户 {result.username}",
        metadata={
            **_actor_metadata(caller),
            "user_id": result.id,
            "username": result.username,
            "changed_fields": body.model_dump(exclude_unset=True),
            "status": result.status,
        },
    )
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: int,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """
    软删除用户。

    Admin:
        可删除所有用户。

    Agent:
        不允许删除用户账户，只能停用用户或停用项目授权。

    注意:
        这是 /api/users/{user_id} 共用删除接口。
        代理端严禁调用 /admin/api/users/{user_id}。
    """
    admin, agent = caller
    await soft_delete_user(
        user_id=user_id,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user.soft_delete",
        target_type="user",
        target_id=user_id,
        summary=f"软删除用户 {user_id}",
        metadata={
            **_actor_metadata(caller),
            "user_id": user_id,
        },
    )


@router.patch("/{user_id}/password", response_model=UserPasswordUpdateResponse)
async def update_user_password_endpoint(
    user_id: int,
    body: UserPasswordUpdateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserPasswordUpdateResponse:
    admin, agent = caller
    result = await update_user_password(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user.password_update",
        target_type="user",
        target_id=user_id,
        summary=f"更新用户 {user_id} 密码",
        metadata={
            **_actor_metadata(caller),
            "user_id": user_id,
            "auto_generate": getattr(body, "auto_generate", None),
        },
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 用户项目授权
# ═══════════════════════════════════════════════════════════════

@router.post(
    "/{user_id}/authorizations/preview",
    response_model=AuthorizationCostPreviewResponse,
    summary="预览授权新项目扣点",
)
async def grant_auth_preview_endpoint(
    user_id: int,
    body: AuthorizationCreateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationCostPreviewResponse:
    admin, agent = caller
    return await preview_authorization_cost(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


@router.post(
    "/{user_id}/authorizations",
    response_model=AuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_auth_endpoint(
    user_id: int,
    body: AuthorizationCreateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationResponse:
    admin, agent = caller
    result = await grant_authorization(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.grant",
        target_type="authorization",
        target_id=result.id,
        summary=f"为用户 {user_id} 授权项目 {result.game_project_id}",
        metadata={
            **_actor_metadata(caller),
            **_authorization_metadata(result),
        },
    )
    return result


@router.patch(
    "/{user_id}/authorizations/{auth_id}",
    response_model=AuthorizationResponse,
)
async def update_auth_endpoint(
    user_id: int,
    auth_id: int,
    body: AuthorizationUpdateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationResponse:
    admin, agent = caller
    result = await update_authorization(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.update",
        target_type="authorization",
        target_id=result.id,
        summary=f"更新用户 {user_id} 授权 {auth_id}",
        metadata={
            **_actor_metadata(caller),
            **_authorization_metadata(result),
            "changed_fields": body.model_dump(exclude_unset=True),
        },
    )
    return result


@router.post(
    "/{user_id}/authorizations/{auth_id}/suspend",
    response_model=AuthorizationResponse,
    summary="停用授权并冻结剩余权益",
)
async def suspend_auth_endpoint(
    user_id: int,
    auth_id: int,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationResponse:
    admin, agent = caller
    result = await suspend_authorization_with_freeze(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.suspend_freeze",
        target_type="authorization",
        target_id=auth_id,
        summary=f"停用用户 {user_id} 授权 {auth_id} 并冻结权益",
        metadata={
            **_actor_metadata(caller),
            **_authorization_metadata(result),
            "user_id": user_id,
            "authorization_id": auth_id,
        },
    )
    return result


@router.post(
    "/{user_id}/authorizations/{auth_id}/enable",
    response_model=AuthorizationResponse,
    summary="启用授权并恢复冻结权益",
)
async def enable_auth_endpoint(
    user_id: int,
    auth_id: int,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationResponse:
    admin, agent = caller
    result = await enable_authorization_with_release(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.enable_release",
        target_type="authorization",
        target_id=auth_id,
        summary=f"启用用户 {user_id} 授权 {auth_id} 并恢复权益",
        metadata={
            **_actor_metadata(caller),
            **_authorization_metadata(result),
            "user_id": user_id,
            "authorization_id": auth_id,
        },
    )
    return result


@router.delete(
    "/{user_id}/authorizations/{auth_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_auth_endpoint(
    user_id: int,
    auth_id: int,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    admin, agent = caller
    await revoke_authorization(
        user_id=user_id,
        auth_id=auth_id,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.revoke",
        target_type="authorization",
        target_id=auth_id,
        summary=f"停用用户 {user_id} 授权 {auth_id}",
        metadata={
            **_actor_metadata(caller),
            "user_id": user_id,
            "authorization_id": auth_id,
        },
    )


@router.post(
    "/{user_id}/authorizations/{auth_id}/renew/preview",
    response_model=AuthorizationRenewPreviewResponse,
    summary="预览授权续费扣点",
)
async def renew_preview_endpoint(
    user_id: int,
    auth_id: int,
    body: AuthorizationRenewRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationRenewPreviewResponse:
    admin, agent = caller
    return await preview_authorization_renew(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


@router.post(
    "/{user_id}/authorizations/{auth_id}/renew",
    response_model=AuthorizationRenewResponse,
    summary="授权续费",
)
async def renew_auth_endpoint(
    user_id: int,
    auth_id: int,
    body: AuthorizationRenewRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationRenewResponse:
    admin, agent = caller
    result = await renew_authorization(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.renew",
        target_type="authorization",
        target_id=auth_id,
        summary=f"续费用户 {user_id} 授权 {auth_id}",
        metadata={
            **_actor_metadata(caller),
            "user_id": user_id,
            "authorization_id": auth_id,
            "old_valid_until": result.old_valid_until.isoformat() if result.old_valid_until else None,
            "new_valid_until": result.new_valid_until.isoformat(),
            "consumed_points": result.consumed_points,
        },
    )
    return result


@router.get(
    "/{user_id}/authorizations/{auth_id}/upgrade/preview",
    response_model=AuthorizationUpgradePreviewResponse,
    summary="预览升级扣点",
)
async def upgrade_preview_endpoint(
    user_id: int,
    auth_id: int,
    additional_devices: int = Query(..., gt=0),
    mode: str = Query(default="append", pattern="^(append|average)$"),
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationUpgradePreviewResponse:
    """预览升级后的到期时间和扣点，不实际执行升级。"""
    admin, agent = caller
    return await preview_authorization_upgrade(
        user_id=user_id,
        auth_id=auth_id,
        additional_devices=additional_devices,
        mode=mode,
        db=db,
        admin=admin,
        agent=agent,
    )


@router.post(
    "/{user_id}/authorizations/{auth_id}/upgrade",
    response_model=AuthorizationUpgradeResponse,
    summary="升级授权设备数",
)
async def upgrade_auth_endpoint(
    user_id: int,
    auth_id: int,
    body: AuthorizationUpgradeRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationUpgradeResponse:
    """
    升级授权设备数（追加/平均两种模式）。

    Admin:
        直接修改，不扣点。

    Agent:
        按模式计算扣点后升级。
    """
    admin, agent = caller
    result = await upgrade_authorization(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
    actor_type, actor_id = _actor(caller)
    await create_audit_log(
        db=db,
        actor_type=actor_type,
        actor_id=actor_id,
        action="user_authorization.upgrade",
        target_type="authorization",
        target_id=auth_id,
        summary=f"升级用户 {user_id} 授权 {auth_id}",
        metadata={
            **_actor_metadata(caller),
            "user_id": user_id,
            "authorization_id": auth_id,
            "additional_devices": body.additional_devices,
            "mode": body.mode,
            "new_devices": result.new_devices,
            "consumed_points": result.consumed_points,
        },
    )
    return result
