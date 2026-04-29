r"""
文件位置: app/routers/balance_agent.py
名称: 代理端余额与定价目录路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理端点数接口。只挂载到 /api/agents。

接口:
      GET /api/agents/my/catalog
      GET /api/agents/catalog
      GET /api/agents/my/balance
      GET /api/agents/my/transactions
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_agent
from app.database import get_main_db
from app.models.main.models import Agent
from app.services.balance_service import (
    get_agent_balance,
    get_all_projects_with_prices,
    get_balance_transactions,
)

router = APIRouter()


@router.get("/my/catalog", summary="全项目定价目录（代理查看，推荐路径）")
async def my_price_catalog(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    return await get_all_projects_with_prices(db)


@router.get("/catalog", summary="全项目定价目录（代理查看，兼容旧路径）")
async def price_catalog_compat(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    return await get_all_projects_with_prices(db)


@router.get("/my/balance", summary="代理查询自己余额")
async def my_balance(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_agent_balance(current_agent.id, db)


@router.get("/my/transactions", summary="代理查询自己流水")
async def my_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tx_type: str | None = Query(default=None),
    related_user_id: int | None = Query(default=None),
    related_project_id: int | None = Query(default=None),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(
        agent_id=current_agent.id,
        db=db,
        page=page,
        page_size=page_size,
        tx_type=tx_type,
        related_user_id=related_user_id,
        related_project_id=related_project_id,
    )