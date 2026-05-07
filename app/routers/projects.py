r"""
文件位置: app/routers/projects.py
名称: 项目管理路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-07
版本: V1.1.0
功能及相关说明:
    POST   /admin/api/projects/                         创建项目（Admin）
    GET    /admin/api/projects/                         项目列表（Admin）
    GET    /admin/api/projects/{id}                     项目详情（Admin）
    PATCH  /admin/api/projects/{id}                     更新项目（Admin）

    POST   /admin/api/agents/{agent_id}/project-auths/         授予代理项目授权（Admin）
    GET    /admin/api/agents/{agent_id}/project-auths/         查询代理项目授权列表（Admin）
    PATCH  /admin/api/agents/{agent_id}/project-auths/{auth_id} 更新授权（Admin）
    DELETE /admin/api/agents/{agent_id}/project-auths/{auth_id} 停用授权（Admin）

改进内容:
    V1.1.0 - 项目管理与代理项目授权关键操作接入 audit_log
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.schemas.project import (
    AgentProjectAuthCreateRequest,
    AgentProjectAuthResponse,
    AgentProjectAuthUpdateRequest,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.audit_service import create_audit_log
from app.services.project_service import (
    create_project,
    get_project,
    grant_agent_project_auth,
    list_agent_project_auths,
    list_projects,
    revoke_agent_project_auth,
    update_agent_project_auth,
    update_project,
)

router = APIRouter()


# ── 项目 CRUD ─────────────────────────────────────────────────

@router.post("/projects/", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(
    body: ProjectCreateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectResponse:
    """创建项目（仅管理员）。游戏项目自动生成 db_name，验证项目无独立数据库。"""
    result = await create_project(body=body, db=db)
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="project.create",
        target_type="game_project",
        target_id=result.id,
        summary=f"创建项目 {result.display_name}",
        metadata={
            "project_id": result.id,
            "game_project_code": result.code_name,
            "display_name": result.display_name,
            "project_type": result.project_type,
            "is_active": result.is_active,
        },
    )
    return result


@router.get("/projects/", response_model=ProjectListResponse)
async def list_projects_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    project_type: str | None = Query(default=None, pattern="^(game|verification)$"),
    is_active: bool | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectListResponse:
    """项目列表（分页 + 类型过滤）。"""
    return await list_projects(
        db=db,
        page=page,
        page_size=page_size,
        project_type=project_type,
        is_active=is_active,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project_endpoint(
    project_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectResponse:
    return await get_project(project_id=project_id, db=db)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(
    project_id: int,
    body: ProjectUpdateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectResponse:
    result = await update_project(project_id=project_id, body=body, db=db)
    changed_fields = body.model_dump(exclude_unset=True)
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="project.update",
        target_type="game_project",
        target_id=result.id,
        summary=f"更新项目 {result.display_name}",
        metadata={
            "project_id": result.id,
            "game_project_code": result.code_name,
            "display_name": result.display_name,
            "project_type": result.project_type,
            "changed_fields": changed_fields,
            "is_active": result.is_active,
        },
    )
    return result


# ── 代理项目授权 ──────────────────────────────────────────────

@router.post(
    "/agents/{agent_id}/project-auths/",
    response_model=AgentProjectAuthResponse,
    status_code=201,
)
async def grant_agent_auth_endpoint(
    agent_id: int,
    body: AgentProjectAuthCreateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthResponse:
    """授予代理对某个项目的操作权限。若已存在授权记录则重新激活并更新到期时间。"""
    result = await grant_agent_project_auth(agent_id=agent_id, body=body, db=db)
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent_project_auth.grant",
        target_type="agent_project_auth",
        target_id=result.id,
        summary=f"授予代理 {agent_id} 项目授权",
        metadata={
            "agent_id": agent_id,
            "auth_id": result.id,
            "project_id": result.project_id,
            "valid_until": result.valid_until.isoformat() if result.valid_until else None,
            "status": result.status,
        },
    )
    return result


@router.get(
    "/agents/{agent_id}/project-auths/",
    response_model=list[AgentProjectAuthResponse],
)
async def list_agent_auths_endpoint(
    agent_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> list[AgentProjectAuthResponse]:
    """查询某代理的所有项目授权。"""
    return await list_agent_project_auths(agent_id=agent_id, db=db)


@router.patch(
    "/agents/{agent_id}/project-auths/{auth_id}",
    response_model=AgentProjectAuthResponse,
)
async def update_agent_auth_endpoint(
    agent_id: int,
    auth_id: int,
    body: AgentProjectAuthUpdateRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthResponse:
    result = await update_agent_project_auth(auth_id=auth_id, body=body, db=db)
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent_project_auth.update",
        target_type="agent_project_auth",
        target_id=result.id,
        summary=f"更新代理 {agent_id} 项目授权 {auth_id}",
        metadata={
            "agent_id": agent_id,
            "auth_id": auth_id,
            "project_id": result.project_id,
            "changed_fields": body.model_dump(exclude_unset=True),
            "valid_until": result.valid_until.isoformat() if result.valid_until else None,
            "status": result.status,
        },
    )
    return result


@router.delete(
    "/agents/{agent_id}/project-auths/{auth_id}",
    status_code=204,
)
async def revoke_agent_auth_endpoint(
    agent_id: int,
    auth_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> None:
    """停用（软删除）代理的项目授权。"""
    await revoke_agent_project_auth(auth_id=auth_id, db=db)
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="agent_project_auth.revoke",
        target_type="agent_project_auth",
        target_id=auth_id,
        summary=f"停用代理 {agent_id} 项目授权 {auth_id}",
        metadata={
            "agent_id": agent_id,
            "auth_id": auth_id,
        },
    )
