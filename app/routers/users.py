r"""
文件位置: app/routers/users.py
文件名称: users.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-29
版本: V1.2.1
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

鉴权:
    - Admin Token：操作所有用户。
    - Agent Token：操作自己创建的用户。
    - 创建者详情目前仅 Admin Token 可访问。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_admin_token, decode_agent_token
from app.database import get_main_db
from app.models.main.models import Admin, Agent
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationResponse,
    AuthorizationUpdateRequest,
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
from app.services.user_service import (
    create_user,
    get_creator_agent_detail,
    get_user,
    grant_authorization,
    list_users,
    revoke_authorization,
    soft_delete_user,
    update_authorization,
    update_user,
    update_user_password,
    upgrade_authorization,
)

router = APIRouter()
_http_bearer = HTTPBearer()


async def _resolve_caller(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> tuple[Admin | None, Agent | None]:
    token = credentials.credentials

    try:
        payload = decode_admin_token(token)
        admin_id = int(payload["sub"])
        result = await db.execute(select(Admin).where(Admin.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin and admin.status == "active":
            return admin, None
    except JWTError:
        pass

    try:
        payload = decode_agent_token(token)
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
    return await create_user(body=body, db=db, admin=admin, agent=agent)


@router.get("/", response_model=UserListResponse)
async def list_users_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    level_filter: str | None = Query(default=None, alias="level"),
    project_id: int | None = Query(default=None, description="按项目过滤"),
    creator_agent_id: int | None = Query(default=None, description="按创建代理过滤，仅管理员使用"),
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
    return await update_user(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


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
        只能删除自己创建的用户。

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


@router.patch("/{user_id}/password", response_model=UserPasswordUpdateResponse)
async def update_user_password_endpoint(
    user_id: int,
    body: UserPasswordUpdateRequest,
    caller: tuple[Admin | None, Agent | None] = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserPasswordUpdateResponse:
    admin, agent = caller
    return await update_user_password(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


# ═══════════════════════════════════════════════════════════════
# 用户项目授权
# ═══════════════════════════════════════════════════════════════

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
    return await grant_authorization(
        user_id=user_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


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
    return await update_authorization(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )


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


@router.get(
    "/{user_id}/authorizations/{auth_id}/upgrade/preview",
    summary="预览升级扣点",
)
async def upgrade_preview_endpoint(
    user_id: int,
    auth_id: int,
    additional_devices: int = Query(..., gt=0),
    mode: str = Query(default="append", pattern="^(append|average)$"),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """预览升级后的到期时间和扣点，不实际执行升级。"""
    from app.services.user_service import _get_user_or_404, _get_authorization_or_404, _get_project_or_404, _ensure_aware
    from app.services.accounting_service import BILLING_RULES, calculate_authorization_cost, _ceil_hours
    from app.models.main.models import ProjectPrice
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from sqlalchemy import select

    await _get_user_or_404(user_id, db)
    auth = await _get_authorization_or_404(user_id, auth_id, db)

    old_devices = int(auth.authorized_devices or 0)
    new_devices = old_devices + additional_devices
    now = datetime.now(timezone.utc)
    remaining = _ceil_hours(now, auth.valid_until) if auth.valid_until else 0
    level_rule = BILLING_RULES.get(auth.user_level, {})
    period_hours = level_rule.get("period_hours", 720)

    price_result = await db.execute(
        select(ProjectPrice).where(
            ProjectPrice.project_id == auth.game_project_id,
            ProjectPrice.user_level == auth.user_level,
        )
    )
    price = price_result.scalar_one_or_none()
    unit_price = Decimal(str(price.points_per_device)) if price else Decimal("0")

    if mode == "average":
        periods = 1  # 整周期
        consumed = float(unit_price * Decimal(str(additional_devices)))
        avg_hours = int((old_devices * remaining + additional_devices * period_hours) / new_devices)
        new_expiry = (now + timedelta(hours=avg_hours)).isoformat()
    else:
        periods = max(1, (remaining + period_hours - 1) // period_hours)
        consumed = float(unit_price * Decimal(str(additional_devices)) * Decimal(str(periods)))
        new_expiry = auth.valid_until.isoformat() if auth.valid_until else None

    return {
        "old_devices": old_devices,
        "new_devices": new_devices,
        "additional_devices": additional_devices,
        "mode": mode,
        "consumed_points": consumed,
        "new_expiry": new_expiry,
        "unit_price": float(unit_price),
        "period_hours": period_hours,
    }


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
    return await upgrade_authorization(
        user_id=user_id,
        auth_id=auth_id,
        body=body,
        db=db,
        admin=admin,
        agent=agent,
    )
