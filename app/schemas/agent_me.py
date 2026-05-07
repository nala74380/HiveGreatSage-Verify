r"""
文件位置: app/schemas/agent_me.py
文件名称: agent_me.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    代理个人主页 /api/agents/me 响应模型。

当前业务口径:
    - hierarchy_depth 表示代理组织层级 / 代理树深度。
    - tier_level 表示代理业务等级 Lv.1 - Lv.4。
    - 不兼容旧字段 level / hierarchy_level。
    - 项目编码对外统一使用 game_project_code。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentMeParentResponse(BaseModel):
    id: int
    username: str
    hierarchy_depth: int = Field(description="上级代理组织层级 / 代理树深度")


class AgentMeProjectResponse(BaseModel):
    id: int
    display_name: str
    game_project_code: str
    project_type: str
    valid_until: datetime | None = None
    is_expired: bool = False


class AgentMeResponse(BaseModel):
    id: int
    username: str
    hierarchy_depth: int = Field(description="代理组织层级 / 代理树深度，不是业务等级")
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    commission_rate: float | None = None
    parent_agent: AgentMeParentResponse | None = None

    users_total: int = 0
    users_active: int = 0
    users_suspended: int = 0
    authorized_projects: list[AgentMeProjectResponse] = Field(default_factory=list)

    tier_level: int = Field(description="代理业务等级 Lv.1 - Lv.4")
    tier_name: str
    risk_status: str
    remark: str | None = None

    credit_limit: float
    max_credit_limit: float
    credit_limit_override: float | None = None
    max_credit_limit_override: float | None = None

    can_create_sub_agents: bool
    max_sub_agents: int
    can_create_sub_agents_override: bool | None = None
    max_sub_agents_override: int | None = None

    can_auto_open_project: bool
    auto_open_project_limit: int
    review_priority: int