r"""
文件位置: app/schemas/agent.py
文件名称: agent.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    代理管理及管理员登录相关的 Pydantic v2 请求/响应模型。
    覆盖：管理员登录、代理登录、代理 CRUD、代理树形结构。

当前业务口径:
    - Agent.level 表示代理组织层级 / 代理树深度。
    - AgentBusinessProfile.tier_level 表示代理业务等级 Lv.1 - Lv.4。
    - 用户数量只作为统计展示，不再作为代理配额硬约束。
    - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。

改进历史:
    V1.1.0 (2026-04-29) - 移除旧账号数量限制口径。
    V1.0.1 (2026-04-25) - 新增 AgentTreeNode / AgentSubtreeResponse，支持 Phase 2 多级代理树形查询。
    V1.0.0 - 初始版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── 管理员登录 ────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=128, examples=["Admin@2026!"])


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token 有效期（秒）", examples=[28800])
    admin_id: int
    username: str


# ── 代理登录 ──────────────────────────────────────────────────

class AgentLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AgentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token 有效期（秒）", examples=[28800])
    agent_id: int
    username: str
    level: int = Field(description="代理组织层级 / 代理树深度，不是业务等级")


# ── 代理 CRUD ─────────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=64,
        description="代理登录名",
        examples=["agent_guangzhou"],
    )
    password: str = Field(
        ..., min_length=6, max_length=128,
        description="初始密码",
    )
    parent_agent_id: int | None = Field(
        default=None,
        description="父代理 ID，None 表示创建顶级代理（由管理员直接管理）",
    )
    commission_rate: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="佣金比例（百分比），可不设置",
    )

    model_config = {"extra": "forbid"}


class AgentUpdateRequest(BaseModel):
    status: Literal["active", "suspended"] | None = Field(
        default=None,
        description="更新状态",
    )
    commission_rate: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="更新佣金比例",
    )

    model_config = {"extra": "forbid"}


class AgentResponse(BaseModel):
    """代理详情响应。"""
    id: int
    username: str
    level: int = Field(description="代理组织层级 / 代理树深度，不是业务等级")
    parent_agent_id: int | None
    created_by_admin_id: int | None
    commission_rate: float | None
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    users_count: int = Field(
        default=0,
        description="该代理直接创建的用户数量，仅作统计，不作为配额限制",
    )

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    """代理列表分页响应。"""
    agents: list[AgentResponse]
    total: int
    page: int
    page_size: int


# ── Phase 2：代理树形结构（WITH RECURSIVE 查询结果）───────────

class AgentTreeNode(BaseModel):
    """
    代理树形节点，递归嵌套表达整棵代理树。

    children 为空列表时表示叶子节点（无下级代理）。
    subtree_user_count 表示该节点及其所有下级代理的用户总数之和（由服务层计算）。
    """
    id: int
    username: str
    level: int = Field(description="代理组织层级 / 代理树深度，不是业务等级")
    parent_agent_id: int | None
    status: str
    commission_rate: float | None
    users_count: int = Field(description="该代理直接创建的用户数，仅作统计")
    subtree_user_count: int = Field(description="该代理及所有下级代理的用户总数，仅作统计")
    children: list[AgentTreeNode] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# 由于 AgentTreeNode 包含自引用（children: list[AgentTreeNode]），
# Pydantic v2 需要调用 model_rebuild() 来完成前向引用解析。
AgentTreeNode.model_rebuild()


class AgentSubtreeResponse(BaseModel):
    """
    代理子树查询响应（含树形结构和统计数据）。

    root 为子树的根节点（如果查询全树则 root.parent_agent_id=None）。
    total_agents 为子树内代理总数（含根节点）。
    total_users 为子树内所有代理的用户总数之和。
    """
    root: AgentTreeNode
    total_agents: int = Field(description="子树内代理总数（含根节点）")
    total_users: int = Field(description="子树内所有用户总数，仅作统计")


class AgentFlatListResponse(BaseModel):
    """
    代理权限范围内的扁平列表（用于分页展示，不含树形嵌套）。
    与 AgentListResponse 区别：此响应包含所有下级代理，不只是直属代理。
    """
    agents: list[AgentResponse]
    total: int
    page: int
    page_size: int