r"""
文件位置: app/schemas/auth.py
文件名称: auth.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    认证相关的 Pydantic v2 请求/响应模型（接口契约）。
    与接入契约.md 保持一致：
      - LoginRequest  : 登录请求体
      - LoginResponse : 登录成功响应
      - RefreshRequest: 刷新 Token 请求体
      - TokenResponse : Token 刷新响应
      - MeResponse    : 当前用户信息响应
改进历史: 无
调试信息: 字段的 examples 会显示在 FastAPI 自动生成的 Swagger 文档中，方便调试。
"""

from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["user001"])
    password: str = Field(..., min_length=1, max_length=128, examples=["MyPassword123"])
    # 客户端登录时传入 game_project.project_uuid（不暴露自增 ID）
    project_uuid: str = Field(
        ...,
        description="游戏项目 UUID（由管理员分配给客户端）",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    # 设备指纹（安卓：hardware_serial；PC：网卡MAC + CPU序列号的哈希）
    device_fingerprint: str = Field(
        ...,
        min_length=8,
        max_length=256,
        description="设备唯一标识",
        examples=["a1b2c3d4e5f6"],
    )
    client_type: str = Field(
        ...,
        description="客户端类型",
        examples=["android"],
        pattern="^(pc|android)$",
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="登录时获取的 Refresh Token")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., description="要吊销的 Refresh Token")


# ── 响应模型 ──────────────────────────────────────────────────

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 有效期（秒）", examples=[900])
    user_id: int
    username: str
    user_level: str
    game_project_code: str = Field(description="登录的游戏项目代码名")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 有效期（秒）", examples=[900])


class MeResponse(BaseModel):
    user_id: int
    username: str
    user_level: str
    status: str
    game_project_code: str


class MessageResponse(BaseModel):
    message: str = Field(examples=["操作成功"])