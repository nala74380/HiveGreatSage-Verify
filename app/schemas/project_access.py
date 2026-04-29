r"""
文件位置: app/schemas/project_access.py
文件名称: project_access.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.2.0
功能说明:
    代理项目准入、项目目录、项目开通申请、管理员审核相关 Pydantic v2 Schema。

当前业务口径:
    - 项目准入使用 AgentBusinessProfile.tier_level。
    - Agent.level 只表示组织层级 / 代理树深度。
    - AgentLevelPolicy 只表达授信、下级代理、自动开通和审核优先级。
    - 用户数量仅作统计展示。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


VisibilityMode = Literal["public", "level_limited", "invite_only", "hidden"]
OpenMode = Literal["manual_review", "auto_by_level", "auto_by_condition", "disabled"]
RequestStatus = Literal["pending", "approved", "rejected", "cancelled", "auto_approved"]

CatalogAccessStatus = Literal[
    "authorized",
    "pending",
    "auto_open_available",
    "apply_available",
    "rejected",
    "unavailable",
]

CatalogActionType = Literal[
    "none",
    "view_request",
    "auto_open",
    "apply",
]


class AgentLevelPolicyResponse(BaseModel):
    """
    代理业务等级策略响应。

    注意:
        这是业务等级策略，不是 Agent.level 组织层级。
    """
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
    """
    管理员端项目准入策略响应。
    """
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
    """
    管理员更新项目准入策略请求。
    """
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


class ProjectPriceCatalogItem(BaseModel):
    """
    代理端项目目录中的项目定价项。
    """
    level: str
    level_name: str
    points: float
    unit_label: str


class AgentProjectCatalogItem(BaseModel):
    """
    代理端项目目录项。

    由 list_agent_project_catalog() 返回。
    表达当前代理对某项目的可见性、申请状态、自动开通状态和已有授权状态。
    """
    id: int
    code_name: str
    display_name: str
    project_type: str

    prices: list[ProjectPriceCatalogItem] = Field(default_factory=list)

    access_status: CatalogAccessStatus
    action_type: CatalogActionType

    is_authorized: bool
    is_visible: bool

    visibility_mode: str
    open_mode: str

    pending_request_id: int | None = None
    last_request_status: str | None = None
    last_request_id: int | None = None
    last_review_note: str | None = None

    auth_valid_until: datetime | None = None


class AgentProjectAuthRequestCreate(BaseModel):
    """
    代理提交项目开通申请请求。
    """
    project_id: int = Field(..., ge=1)
    request_reason: str | None = Field(default=None, max_length=1000)


class AgentProjectAuthRequestResponse(BaseModel):
    """
    代理项目开通申请响应。

    agent_level 当前表示代理业务等级 tier_level。
    """
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
    """
    代理项目开通申请分页响应。
    """
    requests: list[AgentProjectAuthRequestResponse]
    total: int
    page: int
    page_size: int


class ApproveProjectAuthRequest(BaseModel):
    """
    管理员批准代理项目开通申请。
    """
    valid_until: datetime | None = Field(
        default=None,
        description="代理项目授权到期时间，空表示永久",
    )
    review_note: str | None = Field(default=None, max_length=1000)


class RejectProjectAuthRequest(BaseModel):
    """
    管理员拒绝代理项目开通申请。
    """
    review_note: str = Field(..., min_length=1, max_length=1000)