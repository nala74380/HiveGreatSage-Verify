r"""
文件位置: app/routers/project_access_agent.py
文件名称: project_access_agent.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    代理端项目准入、项目目录、项目开通申请接口。

挂载建议:
    app.include_router(project_access_agent.router, prefix="/api/agents/my/project-access")
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
from app.services.project_access_service import (
    cancel_my_project_auth_request,
    create_agent_project_auth_request,
    list_agent_project_catalog,
    list_my_project_auth_requests,
)

router = APIRouter()


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
    return await create_agent_project_auth_request(
        agent=current_agent,
        body=body,
        db=db,
    )


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
    return await cancel_my_project_auth_request(
        request_id=request_id,
        agent=current_agent,
        db=db,
    )