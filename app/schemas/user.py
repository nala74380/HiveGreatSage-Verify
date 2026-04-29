r"""
文件位置: app/schemas/user.py
文件名称: user.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.1.0
功能说明:
    用户管理相关的 Pydantic v2 请求/响应模型。
    覆盖：
      - 用户创建
      - 用户列表/详情
      - 用户更新
      - 用户项目授权
      - 用户密码重置/修改
      - 用户授权项目明细展示

安全边界:
    - 系统不保存用户明文密码。
    - 管理员不能查询旧密码明文。
    - 管理员可以重置密码，并在重置成功响应中一次性看到新密码明文。
    - 代理可以修改/重置密码，但不能查询旧密码。

改进历史:
    V1.1.0 - 增加创建者信息、项目授权明细、设备激活统计、密码修改模型
    V1.0.0 - 初始版本
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── 枚举 ──────────────────────────────────────────────────────

UserLevel = Literal["trial", "normal", "vip", "svip", "tester"]
UserStatus = Literal["active", "suspended", "expired"]


# ── 请求模型 ──────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="登录用户名，3-64 字符",
        examples=["user_001"],
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="初始密码，至少 6 字符",
    )
    user_level: UserLevel = Field(
        default="normal",
        description="用户级别，tester 只有管理员能创建",
    )
    max_devices: int = Field(
        default=500,
        ge=0,
        description="设备绑定上限，0 表示无限制；代理创建用户时不允许 0",
    )
    expired_at: datetime | None = Field(
        default=None,
        description="账号到期时间，None 表示永久有效；代理创建用户时不允许 None",
    )


class UserUpdateRequest(BaseModel):
    status: UserStatus | None = Field(
        default=None,
        description="更新账号状态 active / suspended / expired",
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
        description="更新账号到期时间，传 None 表示永久有效",
    )

    model_config = {"extra": "forbid"}


class UserPasswordUpdateRequest(BaseModel):
    """用户密码修改/重置请求。"""

    new_password: str | None = Field(
        default=None,
        min_length=6,
        max_length=128,
        description="新密码；手动设置时必填",
    )
    auto_generate: bool = Field(
        default=False,
        description="是否自动生成新密码；仅管理员允许使用",
    )

    @model_validator(mode="after")
    def validate_password_source(self):
        if not self.auto_generate and not self.new_password:
            raise ValueError("必须提供 new_password，或设置 auto_generate=true")
        return self


class AuthorizationCreateRequest(BaseModel):
    game_project_id: int = Field(
        ...,
        description="要授权的项目内部 ID",
        examples=[1],
    )
    valid_until: datetime | None = Field(
        default=None,
        description="授权到期时间；代理授权必须提供，管理员可为 None 表示永久",
    )


# ── 响应模型 ──────────────────────────────────────────────────

class AuthorizationInfo(BaseModel):
    """嵌入在 UserResponse 中的项目授权明细。"""

    id: int
    game_project_id: int
    game_project_code: str = Field(description="项目代码名，如 game_001")
    game_project_name: str = Field(description="项目显示名称")
    project_type: str | None = Field(default=None, description="项目类型 game / verification")

    user_level: str = Field(description="该用户当前用户级别")
    user_level_name: str = Field(description="用户级别中文名")

    authorized_devices: int = Field(description="该项目授权设备数，当前等于用户 max_devices")
    activated_devices: int = Field(description="该项目已成功登录激活过的去重设备数")
    inactive_devices: int | None = Field(
        default=None,
        description="未激活设备数；authorized_devices 为 0 表示无限制时为 None",
    )

    valid_from: datetime
    valid_until: datetime | None
    status: str


class AuthorizationResponse(BaseModel):
    """授权接口独立响应。"""

    id: int
    user_id: int
    game_project_id: int
    game_project_code: str
    game_project_name: str
    valid_from: datetime
    valid_until: datetime | None
    status: str

    consumed_points: float = Field(
        default=0.0,
        description="本次授权扣除点数；管理员授权为 0",
    )


class UserPasswordUpdateResponse(BaseModel):
    user_id: int
    username: str
    message: str
    generated_password: str | None = Field(
        default=None,
        description="仅管理员自动生成密码时返回；关闭前端弹窗后不再可查",
    )


class UserResponse(BaseModel):
    """用户详情/列表响应。"""

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
    created_by_type: str = Field(default="unknown", description="admin / agent / unknown")
    created_by_display: str = Field(default="未知", description="创建者显示名")
    created_by_agent_username: str | None = None

    authorizations: list[AuthorizationInfo] = Field(
        default_factory=list,
        description="项目授权明细；列表接口也返回 active 授权明细",
    )

    authorization_count: int = Field(
        default=0,
        description="项目授权总数",
    )
    active_authorization_count: int = Field(
        default=0,
        description="当前有效授权数量",
    )
    active_project_names: list[str] = Field(
        default_factory=list,
        description="当前有效授权的项目名称列表",
    )
    device_binding_count: int = Field(
        default=0,
        description="用户维度已绑定设备数量",
    )

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    page_size: int