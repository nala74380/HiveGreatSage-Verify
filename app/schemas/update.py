r"""
文件位置: app/schemas/update.py
文件名称: update.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.1.1
功能说明:
    热更新接口的 Pydantic v2 请求/响应模型。

    接口说明：
      GET  /api/update/check                          检查是否有新版本（用户 AT）
      GET  /api/update/download                       获取签名下载 URL（用户 AT）
      POST /admin/api/updates/{project_id}/{client_type} 发布新版本（Admin Token，Form 上传）

    说明：
      管理员上传接口使用 Form 参数和 UploadFile，不再使用本文件中的上传请求/响应模型。

改进历史:
    V1.1.1 (2026-05-03): 修正管理员上传路径说明，并移除未使用的 Field 导入
    V1.1.0 (2026-05-03): 删除 VersionUploadRequest/VersionUploadResponse（管理员上传已改为 update_admin.py Form 参数）
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime

from pydantic import BaseModel


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


# 注意：VersionUploadRequest / VersionUploadResponse 已删除。
# 管理员上传功能见 app/routers/update_admin.py（使用 Form 参数，不用这些 schema）。
