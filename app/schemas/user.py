r"""
文件位置: app/schemas/user.py
文件名称: user.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.2.0
功能说明:
    用户管理相关 Pydantic v2 请求/响应模型。

核心口径:
    - 用户是账号主体。
    - 用户等级、授权设备数、到期时间属于 Authorization，即“用户 × 项目授权”。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


UserLevel = Literal["trial", "normal", "vip", "svip", "tester"]
UserStatus = Literal["active", "suspended", "expired"]
AuthorizationStatus = Literal["active", "suspended", "expired"]


# ── 用户请求 ──────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="初始密码")

    model_config = {"extra": "forbid"}


class UserUpdateRequest(BaseModel):
    status: UserStatus | None = Field(default=None, description="账号状态")

    model_config = {"extra": "forbid"}


class UserPasswordUpdateRequest(BaseModel):
    new_password: str | None = Field(default=None, min_length=6, max_length=128)
    auto_generate: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_password_source(self):
        if not self.auto_generate and not self.new_password:
            raise ValueError("必须提供 new_password，或设置 auto_generate=true")
        return self


# ── 授权请求 ──────────────────────────────────────────────────

class AuthorizationCreateRequest(BaseModel):
    game_project_id: int = Field(..., gt=0, description="项目 ID")
    user_level: UserLevel = Field(..., description="该用户在此项目内的授权等级")
    authorized_devices: int = Field(..., ge=0, description="该项目授权设备数，0 表示无限制")
    valid_until: datetime | None = Field(default=None, description="该项目授权到期时间")

    model_config = {"extra": "forbid"}


class AuthorizationUpdateRequest(BaseModel):
    user_level: UserLevel | None = Field(default=None, description="项目内授权等级")
    authorized_devices: int | None = Field(default=None, ge=0, description="项目授权设备数")
    valid_until: datetime | None = Field(default=None, description="项目授权到期时间")
    status: AuthorizationStatus | None = Field(default=None, description="授权状态")

    model_config = {"extra": "forbid"}


# ── 响应模型 ──────────────────────────────────────────────────

class AuthorizationInfo(BaseModel):
    id: int
    game_project_id: int
    game_project_code: str
    game_project_name: str
    project_type: str | None = None

    user_level: str
    user_level_name: str
    authorized_devices: int
    activated_devices: int
    inactive_devices: int | None

    valid_from: datetime
    valid_until: datetime | None
    status: str
    is_expired: bool = False


class AuthorizationResponse(BaseModel):
    id: int
    user_id: int
    game_project_id: int
    game_project_code: str
    game_project_name: str
    user_level: str
    authorized_devices: int
    valid_from: datetime
    valid_until: datetime | None
    status: str
    consumed_points: float = 0.0


class UserPasswordUpdateResponse(BaseModel):
    user_id: int
    username: str
    message: str
    generated_password: str | None = Field(
        default=None,
        description="仅管理员自动生成密码时返回；关闭前端弹窗后不可再次查询",
    )


class UserResponse(BaseModel):
    id: int
    username: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None

    created_by_admin: bool
    created_by_agent_id: int | None
    created_by_type: str = "unknown"
    created_by_display: str = "未知"
    created_by_agent_username: str | None = None

    authorizations: list[AuthorizationInfo] = Field(default_factory=list)
    authorization_count: int = 0
    active_authorization_count: int = 0
    active_project_names: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    page_size: int


class CreatorAgentDetailResponse(BaseModel):
    agent: dict
    users: list[UserResponse]
