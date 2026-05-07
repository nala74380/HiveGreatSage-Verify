r"""
文件位置: app/routers/project_access_agent.py
文件名称: project_access_agent.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-07
版本: V1.1.0
功能说明:
    代理端项目准入、项目目录、项目开通申请接口。

挂载建议:
    app.include_router(project_access_agent.router, prefix="/api/agents/my/project-access")

改进历史:
    V1.1.0 (2026-05-07): 代理提交/取消项目开通申请接入 audit_log。
    V1.0.0 (2026-04-29): 初始版本。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_agent
from app.database import get_main_db
from app.models.main.models import Agent
from app.schemas.project_access import (
    AgentProjectAuthRequestCreate,
    AgentProjectAuthRequestListResponse,
    AgentProjectAuthRequestResponse,
    AgentProjectCatalogItem,
)
from app.services.audit_service import create_audit_log
from app.services.project_access_service import (
    cancel_my_project_auth_request,
    create_agent_project_auth_request,
    list_agent_project_catalog,
    list_my_project_auth_requests,
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


@router.get("/catalog", response_model=list[AgentProjectCatalogItem], summary="代理项目目录（带准入策略）")
async def my_project_catalog(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[AgentProjectCatalogItem]:
    return await list_agent_project_catalog(agent=current_agent, db=db)


@router.post(
    "/requests",
    response_model=AgentProjectAuthRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交项目开通申请 / 满足条件时自动开通",
)
async def create_project_auth_request(
    body: AgentProjectAuthRequestCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestResponse:
    result = await create_agent_project_auth_request(
        agent=current_agent,
        body=body,
        db=db,
    )
    action = (
        "project_access.auto_approve"
        if result.status == "approved"
        else "project_access.request.create"
    )
    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action=action,
        target_type="agent_project_auth_request",
        target_id=result.id,
        summary=f"代理 {current_agent.id} 提交项目 {result.project_id} 开通申请",
        metadata={
            **_request_metadata(result),
            "requested_project_id": body.project_id,
            "agent_username": current_agent.username,
            "agent_hierarchy_depth": current_agent.hierarchy_depth,
        },
    )
    return result


@router.get("/requests", response_model=AgentProjectAuthRequestListResponse, summary="我的项目开通申请")
async def my_project_auth_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestListResponse:
    return await list_my_project_auth_requests(
        agent=current_agent,
        db=db,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/requests/{request_id}/cancel",
    response_model=AgentProjectAuthRequestResponse,
    summary="取消我的待审核项目申请",
)
async def cancel_project_auth_request(
    request_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> AgentProjectAuthRequestResponse:
    result = await cancel_my_project_auth_request(
        request_id=request_id,
        agent=current_agent,
        db=db,
    )
    await create_audit_log(
        db=db,
        actor_type="agent",
        actor_id=current_agent.id,
        action="project_access.request.cancel",
        target_type="agent_project_auth_request",
        target_id=result.id,
        summary=f"代理 {current_agent.id} 取消项目开通申请 {request_id}",
        metadata={
            **_request_metadata(result),
            "agent_username": current_agent.username,
            "agent_hierarchy_depth": current_agent.hierarchy_depth,
        },
    )
    return result
