r"""
文件位置: app/schemas/agent_profile.py
文件名称: agent_profile.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理业务等级、代理业务画像、代理密码重置相关 Schema。

当前业务口径:
    - 代理等级策略不再包含用户配额。
    - 用户数量仅作为统计展示。
    - 代理业务能力由授信、下级代理能力、自动开通能力、风险状态等字段表达。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskStatus = Literal["normal", "watch", "restricted", "frozen"]


class AgentLevelPolicyAdminResponse(BaseModel):
    id: int
    level: int
    level_name: str
    description: str | None = None

    default_credit_limit: float
    max_credit_limit: float

    can_create_sub_agents: bool
    max_sub_agents: int

    can_auto_open_project: bool
    auto_open_project_limit: int
    review_priority: int

    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentLevelPolicyUpdateRequest(BaseModel):
    level_name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)

    default_credit_limit: float | None = Field(default=None, ge=0)
    max_credit_limit: float | None = Field(default=None, ge=0)

    can_create_sub_agents: bool | None = None
    max_sub_agents: int | None = Field(default=None, ge=0)

    can_auto_open_project: bool | None = None
    auto_open_project_limit: int | None = Field(default=None, ge=0)
    review_priority: int | None = Field(default=None, ge=0)

    is_active: bool | None = None

    model_config = {"extra": "forbid"}


class AgentBusinessProfileResponse(BaseModel):
    agent_id: int
    username: str

    hierarchy_level: int = Field(description="代理组织层级 / 代理树深度")
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

    level_policy: AgentLevelPolicyAdminResponse | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentBusinessProfileUpdateRequest(BaseModel):
    tier_level: int | None = Field(default=None, ge=1, le=4)

    credit_limit_override: float | None = Field(default=None, ge=0)
    max_credit_limit_override: float | None = Field(default=None, ge=0)

    can_create_sub_agents_override: bool | None = None
    max_sub_agents_override: int | None = Field(default=None, ge=0)

    risk_status: RiskStatus | None = None
    remark: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class AgentPasswordResetRequest(BaseModel):
    auto_generate: bool = Field(default=True)
    new_password: str | None = Field(default=None, min_length=6, max_length=128)


class AgentPasswordResetResponse(BaseModel):
    agent_id: int
    username: str
    generated_password: str | None = None