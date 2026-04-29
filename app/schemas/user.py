r"""
文件位置: app/schemas/user.py
文件名称: user.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    用户管理相关的 Pydantic v2 请求/响应模型。
    覆盖：用户创建、查询（列表/详情）、更新、授权管理。

    user_level 枚举：trial / normal / vip / svip / tester
    与数据库 CHECK 约束 chk_user_level_enum 保持一致。

关联文档:
    [[01-网络验证系统/数据库设计]] 2.3 用户表

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 用户级别枚举（与数据库 CHECK 约束对齐）
UserLevel = Literal["trial", "normal", "vip", "svip", "tester"]
UserStatus = Literal["active", "suspended", "expired"]


# ── 请求模型 ──────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=64,
        description="登录用户名，3-64 字符",
        examples=["user_001"],
    )
    password: str = Field(
        ..., min_length=6, max_length=128,
        description="初始密码，至少 6 字符",
    )
    user_level: UserLevel = Field(
        default="normal",
        description="用户级别，tester 只有管理员能创建",
    )
    max_devices: int = Field(
        default=500,
        ge=0,
        description="设备绑定上限，0 表示无限制",
    )
    expired_at: datetime | None = Field(
        default=None,
        description="账号到期时间，None 表示永久有效",
    )


class UserUpdateRequest(BaseModel):
    status: UserStatus | None = Field(
        default=None,
        description="更新账号状态（active / suspended）",
    )
    user_level: UserLevel | None = Field(
        default=None,
        description="更新用户级别",
    )
    max_devices: int | None = Field(
        default=None,
        ge=0,
        description="更新设备绑定上限，0 表示无限制",
    )
    expired_at: datetime | None = Field(
        default=None,
        description="更新到期时间，传 None 表示设为永久有效",
    )

    model_config = {"extra": "forbid"}   # 拒绝未知字段，防止误操作


class AuthorizationCreateRequest(BaseModel):
    game_project_id: int = Field(
        ...,
        description="要授权的游戏项目内部 ID",
        examples=[1],
    )
    valid_until: datetime | None = Field(
        default=None,
        description="授权到期时间，None 表示永久有效",
    )


# ── 响应模型 ──────────────────────────────────────────────────

class AuthorizationInfo(BaseModel):
    """嵌入在 UserResponse 中的授权简要信息。"""
    id: int
    game_project_id: int
    game_project_code: str = Field(description="游戏项目代码名，如 game_001")
    game_project_name: str = Field(description="游戏项目显示名称")
    valid_from: datetime
    valid_until: datetime | None
    status: str


class AuthorizationResponse(BaseModel):
    """授权接口独立响应（grant/revoke 的返回值）。"""
    id: int
    user_id: int
    game_project_id: int
    game_project_code: str
    game_project_name: str
    valid_from: datetime
    valid_until: datetime | None
    status: str


class UserResponse(BaseModel):
    """用户详情（detail 接口返回，含授权列表）。"""
    id: int
    username: str
    user_level: str
    status: str
    max_devices: int
    created_at: datetime
    updated_at: datetime | None = None
    expired_at: datetime | None
    created_by_admin: bool
    created_by_agent_id: int | None
    authorizations: list[AuthorizationInfo] = Field(
        default_factory=list,
        description="当前有效的游戏授权列表（列表接口中此字段为空）",
    )
    # 列表接口额外返回的计数字段（detail 接口中可从 authorizations 推算，此处冗余方便前端）
    authorization_count: int = Field(
        default=0,
        description="该用户的游戏授权总数（含已 suspended）",
    )
    active_authorization_count: int = Field(
        default=0,
        description="当前有效（active）的游戏授权数量",
    )
    active_project_names: list[str] = Field(
        default_factory=list,
        description="当前有效授权的项目名称列表",
    )
    device_binding_count: int = Field(
        default=0,
        description="已绑定（bound）的设备数量",
    )

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """用户列表分页响应。"""
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
