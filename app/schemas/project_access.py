r"""
文件位置: app/schemas/project_access.py
文件名称: project_access.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理项目准入、申请、审核相关 Pydantic v2 Schema。

当前业务口径:
    - 项目准入使用 AgentBusinessProfile.tier_level。
    - Agent.level 只表示组织层级 / 代理树深度。
    - 代理等级策略只表达授信、下级代理、自动开通和审核优先级。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


VisibilityMode = Literal["public", "level_limited", "invite_only", "hidden"]
OpenMode = Literal["manual_review", "auto_by_level", "auto_by_condition", "disabled"]
RequestStatus = Literal["pending", "approved", "rejected", "cancelled", "auto_approved"]


class AgentLevelPolicyResponse(BaseModel):
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

    model_config = {"from_attributes": True}


class ProjectAccessPolicyResponse(BaseModel):
    id: int
    project_id: int
    project_name: str | None = None
    project_code: str | None = None
    project_type: str | None = None

    visibility_mode: str
    open_mode: str
    min_visible_agent_level: int
    min_apply_agent_level: int
    min_auto_open_agent_level: int | None
    min_available_points: float
    allow_apply: bool
    allow_auto_open: bool
    require_request_reason: bool
    cooldown_hours_after_reject: int
    is_active: bool

    model_config = {"from_attributes": True}


class ProjectAccessPolicyUpdateRequest(BaseModel):
    visibility_mode: VisibilityMode | None = None
    open_mode: OpenMode | None = None

    min_visible_agent_level: int | None = Field(default=None, ge=1, le=4)
    min_apply_agent_level: int | None = Field(default=None, ge=1, le=4)
    min_auto_open_agent_level: int | None = Field(default=None, ge=1, le=4)

    min_available_points: float | None = Field(default=None, ge=0)
    allow_apply: bool | None = None
    allow_auto_open: bool | None = None
    require_request_reason: bool | None = None
    cooldown_hours_after_reject: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    model_config = {"extra": "forbid"}


class AgentProjectAuthRequestCreate(BaseModel):
    project_id: int = Field(..., ge=1)
    request_reason: str | None = Field(default=None, max_length=1000)


class AgentProjectAuthRequestResponse(BaseModel):
    id: int
    agent_id: int
    agent_username: str | None = None
    agent_level: int | None = None

    project_id: int
    project_name: str | None = None
    project_code: str | None = None

    request_reason: str | None = None
    status: str

    reviewed_by_admin_id: int | None = None
    reviewed_by_admin_username: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    auto_approve_reason: str | None = None

    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentProjectAuthRequestListResponse(BaseModel):
    requests: list[AgentProjectAuthRequestResponse]
    total: int
    page: int
    page_size: int


class ApproveProjectAuthRequest(BaseModel):
    valid_until: datetime | None = Field(default=None, description="代理项目授权到期时间，空表示永久")
    review_note: str | None = Field(default=None, max_length=1000)


class RejectProjectAuthRequest(BaseModel):
    review_note: str = Field(..., min_length=1, max_length=1000)