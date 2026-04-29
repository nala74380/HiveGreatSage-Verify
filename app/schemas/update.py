r"""
文件位置: app/schemas/update.py
文件名称: update.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.1
功能说明:
    热更新接口的 Pydantic v2 请求/响应模型。

    接口说明：
      GET  /api/update/check           检查是否有新版本（用户 AT）
      GET  /api/update/download        获取签名下载 URL（用户 AT）
      POST /admin/api/updates/         发布新版本（Admin Token，C06 新增）

改进历史:
    V1.0.1 (2026-04-25) - 新增 VersionUploadRequest / VersionUploadResponse（C06）
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClientType = Literal["pc", "android"]


# ── GET /api/update/check 响应 ────────────────────────────────

class UpdateCheckResponse(BaseModel):
    """版本检查响应。need_update=False 时其余字段为 None。"""
    need_update: bool
    current_version: str
    client_type: str
    game_project_code: str
    force_update: bool | None = None
    release_notes: str | None = None
    checksum_sha256: str | None = None


# ── GET /api/update/download 响应 ────────────────────────────

class UpdateDownloadResponse(BaseModel):
    """签名下载 URL 响应，有效期由 S3_URL_EXPIRE_SECONDS 控制（默认 10 分钟）。"""
    download_url: str
    expires_at: datetime
    version: str
    checksum_sha256: str | None = None


# ── POST /admin/api/updates/ 请求/响应（C06 新增）─────────────

class VersionUploadRequest(BaseModel):
    """
    发布新版本请求（管理员上传热更新包）。

    file_data 为 base64 编码的文件内容，或通过 multipart/form-data 上传（二选一）。
    当前实现使用 multipart/form-data，此 schema 仅用于元数据字段校验。

    package_path 可选：
      若不填，由服务端按约定规则自动生成：
        {game_code}/{client_type}/packages/{version}/{game_code}_{client_type}_{version}.{ext}
      若填写，以传入的路径为准（绝对路径会被拒绝，只接受相对路径）。
    """
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="版本号，格式 MAJOR.MINOR.PATCH，如 1.0.1",
        examples=["1.0.1"],
    )
    client_type: ClientType = Field(
        ...,
        description="客户端类型：pc 或 android",
        examples=["android"],
    )
    force_update: bool = Field(
        default=False,
        description="是否强制更新；True 时客户端不更新则无法继续运行",
    )
    release_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="版本更新说明，显示在客户端更新提示中",
        examples=["修复找图精度问题，优化内存占用"],
    )


class VersionUploadResponse(BaseModel):
    """发布新版本响应。"""
    id: int = Field(description="新版本记录 ID")
    version: str
    client_type: str
    package_path: str = Field(description="文件在存储中的相对路径")
    checksum_sha256: str = Field(description="服务端计算的 SHA-256 校验值")
    force_update: bool
    release_notes: str | None
    released_at: datetime
    game_project_code: str
    message: str = Field(description="操作结果说明", examples=["版本 1.0.1 发布成功，旧版本已归档"])
