r"""
文件位置: app/routers/update.py
文件名称: update.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.1
功能说明:
    热更新路由（客户端专用）：
      GET /api/update/check    — 检查是否有新版本
      GET /api/update/download — 获取签名限时下载 URL

    调用方：
      check    → PC 中控（每次启动）/ 安卓脚本（登录后）
      download → 客户端确认需要更新后调用，获取下载链接

    路由层职责：
      1. 鉴权（get_current_user + get_game_project_code）
      2. 获取主库 Session 和 Redis 连接
      3. 调用 update_service，返回 HTTP 响应
      不包含任何业务判断逻辑。

    Query 参数说明：
      client_type     : "pc" 或 "android"
      current_version : 客户端当前版本号，格式 MAJOR.MINOR.PATCH（如 1.0.0）

关联文档:
    [[01-网络验证系统/架构设计]] 第十节 热更新机制

改进历史:
    V1.0.1 (2026-05-03): 修正文档说明，热更新版本记录已迁至主库，不再写“游戏库 Session”
    V1.0.0 - 从空桩重写为完整实现
调试信息:
    已知问题: 无
    client_type 枚举限制在 Query 层做，不合法时返回 422 Unprocessable Entity
"""

from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_game_project_code
from app.core.redis_client import get_redis
from app.database import get_main_db
from app.models.main.models import User
from app.schemas.update import UpdateCheckResponse, UpdateDownloadResponse
from app.services.update_service import check_update, get_download_url

router = APIRouter()


@router.get("/check", response_model=UpdateCheckResponse, summary="检查版本更新")
async def check_update_endpoint(
    client_type: Literal["pc", "android"] = Query(
        ...,
        description="客户端类型：pc 或 android",
        examples=["android"],
    ),
    current_version: str = Query(
        ...,
        description="客户端当前版本号，格式 MAJOR.MINOR.PATCH",
        examples=["1.0.0"],
        pattern=r"^\d+\.\d+\.\d+$",
    ),
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> UpdateCheckResponse:
    """
    检查当前游戏项目是否有新版本。

    - `need_update=false`：客户端已是最新，无需处理
    - `need_update=true`，`force_update=false`：建议更新，可跳过
    - `need_update=true`，`force_update=true`：必须更新，不更新则阻止运行

    安卓脚本调用示例：
    ```
    GET /api/update/check?client_type=android&current_version=1.0.0
    Authorization: Bearer {access_token}
    ```
    """
    return await check_update(
        current_version=current_version,
        client_type=client_type,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )


@router.get("/download", response_model=UpdateDownloadResponse, summary="获取下载链接")
async def download_update_endpoint(
    client_type: Literal["pc", "android"] = Query(
        ...,
        description="客户端类型：pc 或 android",
        examples=["android"],
    ),
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
    main_db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> UpdateDownloadResponse:
    """
    获取当前游戏项目最新版本的签名下载 URL（有效期 10 分钟）。

    URL 过期后需重新调用此接口获取新链接。
    下载完成后请校验 `checksum_sha256` 确保文件完整性。

    安卓脚本调用示例：
    ```
    GET /api/update/download?client_type=android
    Authorization: Bearer {access_token}
    ```
    """
    return await get_download_url(
        client_type=client_type,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )
