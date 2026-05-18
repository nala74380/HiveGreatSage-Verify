r"""
文件位置: app/schemas/auth.py
文件名称: auth.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    认证相关的 Pydantic v2 请求 / 响应模型。

    当前整改边界:
      1. /api/auth/me 不再把 User.user_level 作为授权等级返回。
      2. /api/auth/me 返回当前 Token 项目上下文下的 Authorization 授权摘要。
      3. LoginResponse 返回 authorization_level / game_project_code。

改进历史:
    V1.1.0 (2026-05-02) - MeResponse 改为 Authorization 授权摘要口径。
    V1.0.0 - 初始认证接口契约。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["user001"])
    password: str = Field(..., min_length=1, max_length=128, examples=["MyPassword123"])
    project_uuid: str = Field(
        ...,
        description="游戏项目 UUID（由管理员分配给客户端）",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    device_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="设备编号；同一账号、同一项目下唯一",
        examples=["A118"],
    )
    client_type: str = Field(
        ...,
        description="客户端类型",
        examples=["android"],
        pattern="^(pc|android)$",
    )

    @field_validator("device_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="登录时获取的 Refresh Token")
    device_id: str = Field(..., min_length=1, max_length=64, description="当前设备编号，必须与 RT 绑定设备一致")
    client_type: str = Field(..., pattern="^(pc|android)$", description="当前客户端类型，必须与 RT 绑定客户端一致")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., description="要吊销的 Refresh Token")


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 有效期（秒）", examples=[900])
    user_id: int
    username: str
    game_project_id: int | None = None
    authorization_id: int | None = None
    authorization_level: str
    game_project_code: str = Field(description="登录的游戏项目代码名")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 有效期（秒）", examples=[900])


class MeResponse(BaseModel):
    """
    当前用户信息响应。

    重要边界:
      1. authorization_level 来自 Authorization.user_level。
      2. authorized_devices 来自 Authorization.authorized_devices。
      3. valid_until 来自 Authorization.valid_until。
      4. 不再返回旧 User.user_level 作为授权等级。
    """

    user_id: int
    username: str
    status: str

    game_project_id: int
    game_project_code: str

    authorization_id: int
    authorization_level: str
    authorized_devices: int = Field(description="授权设备总数")
    activated_devices: int = Field(description="已激活设备数")
    inactive_devices: int | None = Field(default=None, description="未激活设备数（无限制时为 None）")
    valid_until: datetime | None = None


class MessageResponse(BaseModel):
    message: str = Field(examples=["操作成功"])
