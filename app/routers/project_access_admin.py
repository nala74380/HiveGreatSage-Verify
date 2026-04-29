r"""
文件位置: app/routers/project_access_admin.py
文件名称: project_access_admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    管理员端项目准入策略与代理项目开通申请审核接口。

挂载建议:
    app.include_router(project_access_admin.router, prefix="/admin/api/project-access")
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.models import Admin
from app.schemas.project_access import (
    AgentProjectAuthRequestListResponse,
    AgentProjectAuthRequestResponse,
    ApproveProjectAuthRequest,
    ProjectAccessPolicyResponse,
    ProjectAccessPolicyUpdateRequest,
    RejectProjectAuthRequest,
)
from app.services.project_access_service import (
    approve_project_auth_request,
    list_all_project_auth_requests,
    list_project_access_policies,
    reject_project_auth_request,
    update_project_access_policy,
)

router = APIRouter()


@router.get("/policies", summary="项目准入策略列表")
async def project_access_policies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await list_project_access_policies(
        db=db,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/policies/{project_id}",
    response_model=ProjectAccessPolicyResponse,
    summary="更新项目准入策略",
)
async def update_policy(
    project_id: int,
    body: ProjectAccessPolicyUpdateRequest,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectAccessPolicyResponse:
    return await update_project_access_policy(
        project_id=project_id,
        body=body,
        db=db,
    )


@router.get(
    "/requests",
    response_model=AgentProjectAuthRequestListResponse,
    summary="代理项目开通申请列表",
)
async def project_auth_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    agent_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestListResponse:
    return await list_all_project_auth_requests(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        agent_id=agent_id,
        project_id=project_id,
    )


@router.post(
    "/requests/{request_id}/approve",
    response_model=AgentProjectAuthRequestResponse,
    summary="批准代理项目开通申请",
)
async def approve_request(
    request_id: int,
    body: ApproveProjectAuthRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestResponse:
    return await approve_project_auth_request(
        request_id=request_id,
        body=body,
        admin=current_admin,
        db=db,
    )


@router.post(
    "/requests/{request_id}/reject",
    response_model=AgentProjectAuthRequestResponse,
    summary="拒绝代理项目开通申请",
)
async def reject_request(
    request_id: int,
    body: RejectProjectAuthRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestResponse:
    return await reject_project_auth_request(
        request_id=request_id,
        body=body,
        admin=current_admin,
        db=db,
    )