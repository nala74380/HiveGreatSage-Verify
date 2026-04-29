r"""
文件位置: app/services/balance_service.py
文件名称: balance_service.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V2.0.1
功能说明:
    兼容层。

重构说明:
    账务中心已升级为独立业务域，正式服务层为:
        app/services/accounting_service.py

    本文件只保留旧函数名、旧常量名并转发到 accounting_service，
    目的是让旧路由和旧调用方暂时无需一次性大改。

为什么仍然保留这些导出:
    旧 user_service.py 仍从 balance_service 导入:
        - LEVEL_NAMES
        - consume_agent_authorization_points
        - refund_user_authorization_points_on_delete

    如果兼容层不导出旧符号，FastAPI 启动时会 ImportError。

后续计划:
    1. 新增 app/routers/accounting.py 已完成。
    2. 前端切换到账务中心接口。
    3. user_service.py 后续逐步改为直接引用 accounting_service。
    4. balance_service.py 最终删除。
"""

from app.services.accounting_service import (
    BALANCE_TYPE_LABELS,
    BILLING_RULES,
    LEVEL_NAMES,
    PRICING_LEVELS,
    TX_TYPE_LABELS,
    calculate_authorization_cost,
    consume_agent_authorization_points,
    credit_agent,
    delete_project_price,
    freeze_credit,
    get_agent_balance,
    get_agents_with_balance_and_projects,
    get_all_projects_with_prices,
    get_balance_transactions,
    get_project_prices,
    recharge_agent,
    refund_user_authorization_points_on_delete,
    set_project_price,
    unfreeze_credit,
)

__all__ = [
    "BALANCE_TYPE_LABELS",
    "BILLING_RULES",
    "LEVEL_NAMES",
    "PRICING_LEVELS",
    "TX_TYPE_LABELS",
    "calculate_authorization_cost",
    "consume_agent_authorization_points",
    "credit_agent",
    "delete_project_price",
    "freeze_credit",
    "get_agent_balance",
    "get_agents_with_balance_and_projects",
    "get_all_projects_with_prices",
    "get_balance_transactions",
    "get_project_prices",
    "recharge_agent",
    "refund_user_authorization_points_on_delete",
    "set_project_price",
    "unfreeze_credit",
]