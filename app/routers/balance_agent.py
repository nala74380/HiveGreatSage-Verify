r"""
文件位置: app/routers/balance_agent.py
名称: 代理端余额与定价目录路由
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-29
版本: V1.0.0
功能说明:
    代理端点数接口。只挂载到 /api/agents，避免 Admin 管理接口与 Agent 自查接口
    共用 router 导致非预期路径暴露。

    代理可访问：
      GET /api/agents/catalog
      GET /api/agents/my/balance
      GET /api/agents/my/transactions

改进内容:
    V1.0.0 - 从 app/routers/balance.py 拆分 Agent 路由，治理 balance.router 双前缀挂载问题
调试信息:
    若代理浏览器“项目目录/余额”页面 404，先检查 app/main.py 是否注册 balance_agent.router 到 /api/agents。
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


@router.get("/catalog", summary="全项目定价目录（代理查看）")
async def price_catalog(
    _: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> list[dict]:
    """代理查看所有项目的定价，并可申请授权。"""
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
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    return await get_balance_transactions(current_agent.id, db, page, page_size)