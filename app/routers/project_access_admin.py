r"""
文件位置: app/routers/project_access_admin.py
文件名称: project_access_admin.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-07
版本: V1.1.0
功能说明:
    管理员端项目准入策略与代理项目开通申请审核接口。

挂载建议:
    app.include_router(project_access_admin.router, prefix="/admin/api/project-access")

改进历史:
    V1.1.0 (2026-05-07): 项目准入策略更新、批准/拒绝申请接入 audit_log。
    V1.0.0 (2026-04-29): 初始版本。
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
from app.services.audit_service import create_audit_log
from app.services.project_access_service import (
    approve_project_auth_request,
    list_all_project_auth_requests,
    list_project_access_policies,
    reject_project_auth_request,
    update_project_access_policy,
)

router = APIRouter()


def _request_metadata(result: AgentProjectAuthRequestResponse) -> dict:
    """生成项目开通申请审计元数据。"""
    return {
        "request_id": result.id,
        "agent_id": result.agent_id,
        "project_id": result.project_id,
        "status": result.status,
        "reason": result.reason,
        "review_note": result.review_note,
        "requested_at": result.requested_at.isoformat() if result.requested_at else None,
        "reviewed_at": result.reviewed_at.isoformat() if result.reviewed_at else None,
    }


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
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> ProjectAccessPolicyResponse:
    result = await update_project_access_policy(
        project_id=project_id,
        body=body,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="project_access.policy.update",
        target_type="project_access_policy",
        target_id=project_id,
        summary=f"更新项目 {project_id} 准入策略",
        metadata={
            "project_id": project_id,
            "changed_fields": body.model_dump(exclude_unset=True),
            "min_agent_level": result.min_agent_level,
            "allow_auto_approve": result.allow_auto_approve,
            "is_active": result.is_active,
        },
    )
    return result


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
    result = await approve_project_auth_request(
        request_id=request_id,
        body=body,
        admin=current_admin,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="project_access.request.approve",
        target_type="agent_project_auth_request",
        target_id=result.id,
        summary=f"批准代理 {result.agent_id} 项目 {result.project_id} 开通申请",
        metadata={
            **_request_metadata(result),
            "valid_until": body.valid_until.isoformat() if body.valid_until else None,
            "review_note": body.review_note,
        },
    )
    return result


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
    result = await reject_project_auth_request(
        request_id=request_id,
        body=body,
        admin=current_admin,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="project_access.request.reject",
        target_type="agent_project_auth_request",
        target_id=result.id,
        summary=f"拒绝代理 {result.agent_id} 项目 {result.project_id} 开通申请",
        metadata={
            **_request_metadata(result),
            "review_note": body.review_note,
        },
    )
    return result
