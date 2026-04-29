r"""
文件位置: app/schemas/project.py
名称: 项目管理 Pydantic 模型
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能及相关说明:
    覆盖：项目 CRUD、代理项目授权 CRUD。

改进内容:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── 项目类型枚举（字符串常量） ─────────────────────────────────
PROJECT_TYPE_GAME         = "game"          # 游戏项目（需独立数据库）
PROJECT_TYPE_VERIFICATION = "verification"  # 普通验证项目（仅验证服务）


# ── 项目 CRUD ─────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    display_name: str = Field(
        ..., min_length=1, max_length=128,
        description="项目显示名称",
        examples=["某某手游 2026"],
    )
    code_name: str = Field(
        ..., min_length=2, max_length=64,
        pattern=r"^[a-z0-9_]+$",
        description="项目代号（小写字母/数字/下划线），同时作为数据库名后缀",
        examples=["game_001"],
    )
    project_type: str = Field(
        default=PROJECT_TYPE_GAME,
        pattern=f"^({PROJECT_TYPE_GAME}|{PROJECT_TYPE_VERIFICATION})$",
        description=(
            "game=游戏项目（自动创建独立数据库 hive_{{code_name}}）；"
            "verification=普通验证项目（仅验证服务，无独立数据库）"
        ),
    )


class ProjectUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = Field(default=None, description="是否启用")

    model_config = {"extra": "forbid"}


class ProjectResponse(BaseModel):
    id: int
    project_uuid: UUID
    code_name: str
    display_name: str
    project_type: str
    db_name: str | None          # 游戏项目才有，验证项目为 None
    is_active: bool
    created_at: datetime
    # 统计
    authorized_user_count: int = Field(default=0, description="已授权的用户数量")
    authorized_agent_count: int = Field(default=0, description="已授权的代理数量")

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
    page: int
    page_size: int


# ── 代理项目授权 CRUD ─────────────────────────────────────────

class AgentProjectAuthCreateRequest(BaseModel):
    project_id: int = Field(..., description="要授权的项目 ID")
    valid_until: datetime | None = Field(
        default=None,
        description="授权到期时间，None = 永久有效",
    )


class AgentProjectAuthUpdateRequest(BaseModel):
    status: str | None = Field(
        default=None,
        pattern="^(active|suspended)$",
    )
    valid_until: datetime | None = Field(default=None)

    model_config = {"extra": "forbid"}


class AgentProjectAuthResponse(BaseModel):
    id: int
    agent_id: int
    project_id: int
    project_display_name: str
    project_type: str
    valid_until: datetime | None
    status: str
    granted_at: datetime

    model_config = {"from_attributes": True}
