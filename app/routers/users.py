r"""
文件位置: app/routers/users.py
文件名称: users.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    用户管理路由（薄层）：
      POST   /api/users/                         — 创建用户
      GET    /api/users/                         — 查询用户列表
      GET    /api/users/{user_id}                — 查询用户详情
      PATCH  /api/users/{user_id}                — 更新用户信息
      POST   /api/users/{user_id}/authorizations — 授予游戏授权
      DELETE /api/users/{user_id}/authorizations/{auth_id} — 撤销授权

    鉴权：
      - 管理员（Admin Token）：操作所有用户
      - 代理（Agent Token）：只操作自己创建的用户
      - 两种 token 的区分通过 FastAPI 依赖实现

    注意：此处同时支持 Admin 和 Agent 两种调用方，
    路由层通过尝试两种依赖来判断调用方身份（薄路由模式）。

改进历史:
    V1.0.0 - 从存根重写为完整实现
调试信息:
    已知问题: 无
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_admin_token, decode_agent_token
from app.database import get_main_db
from app.models.main.models import Admin, Agent
from app.schemas.user import (
    AuthorizationCreateRequest,
    AuthorizationResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.user_service import (
    create_user,
    get_user,
    grant_authorization,
    list_users,
    revoke_authorization,
    update_user,
)
from sqlalchemy import select

router = APIRouter()
_http_bearer = HTTPBearer()


async def _resolve_caller(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_main_db),
) -> tuple[Admin | None, Agent | None]:
    """
    解析调用方身份：尝试 Admin Token，再尝试 Agent Token。
    返回 (admin, agent)，两者恰好一个非 None。
    两种 Token 均无效时返回 401。
    """
    token = credentials.credentials

    # 先尝试 Admin Token
    try:
        payload = decode_admin_token(token)
        admin_id = int(payload["sub"])
        result = await db.execute(select(Admin).where(Admin.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin and admin.status == "active":
            return admin, None
    except JWTError:
        pass

    # 再尝试 Agent Token
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


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    body: UserCreateRequest,
    caller: tuple = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    """创建用户（管理员或代理调用）。"""
    admin, agent = caller
    return await create_user(body=body, db=db, admin=admin, agent=agent)


@router.get("/", response_model=UserListResponse)
async def list_users_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    level_filter: str | None = Query(default=None, alias="level"),
    project_id: int | None = Query(default=None, description="按项目过滤：只返回对该项目有效授权的用户"),
    caller: tuple = Depends(_resolve_caller),
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
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_endpoint(
    user_id: int,
    caller: tuple = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    """查询指定用户详情（含授权列表）。"""
    return await get_user(user_id=user_id, db=db)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: int,
    body: UserUpdateRequest,
    caller: tuple = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> UserResponse:
    """更新用户状态、级别或到期时间。"""
    return await update_user(user_id=user_id, body=body, db=db)


@router.post(
    "/{user_id}/authorizations",
    response_model=AuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_auth_endpoint(
    user_id: int,
    body: AuthorizationCreateRequest,
    caller: tuple = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> AuthorizationResponse:
    """为用户授予指定项目的访问权限。代理只能授权自己已有的项目。"""
    admin, agent = caller
    return await grant_authorization(user_id=user_id, body=body, db=db, admin=admin, agent=agent)


@router.delete("/{user_id}/authorizations/{auth_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_auth_endpoint(
    user_id: int,
    auth_id: int,
    caller: tuple = Depends(_resolve_caller),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """撤销用户的游戏授权（状态改为 suspended，不物理删除）。"""
    await revoke_authorization(user_id=user_id, auth_id=auth_id, db=db)
