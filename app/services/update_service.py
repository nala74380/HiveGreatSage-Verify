r"""
文件位置: app/services/update_service.py
文件名称: update_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.1.1
功能说明:
    热更新服务层（客户端检查/下载）：
      - check_update()      检查版本、比较、返回是否需要更新
      - get_download_url()  生成带签名的限时下载 URL

    版本比较规则：
      只比较 MAJOR.MINOR.PATCH 三段，任意一段服务端更大则触发更新。

    Redis 缓存策略：
      Key: update:latest:{game_project_code}:{client_type}
      TTL: 300 秒（5 分钟）

    管理员上传功能见 app/routers/update_admin.py。

关联文档:
    [[01-网络验证系统/架构设计]] 第十节 热更新机制

改进历史:
    V1.1.1 (2026-05-03): 修复 get_download_url() 调用 get_storage() 时缺少导入的问题
    V1.1.0 (2026-05-03): 删除 upload_version() 和 invalidate_version_cache()（已由 update_admin.py 取代）；
                        客户端查询切换到主库 VersionRecord
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.storage import get_storage
from app.models.main.models import GameProject, VersionRecord
from app.schemas.update import (
    UpdateCheckResponse,
    UpdateDownloadResponse,
)

_CACHE_KEY = "update:latest:{game_project_code}:{client_type}"
_CACHE_TTL = 300  # 5 分钟


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def check_update(
    current_version: str,
    client_type: str,
    game_project_code: str,
    main_db: AsyncSession,
    redis,
) -> UpdateCheckResponse:
    """
    检查是否有新版本。

    流程：
      1. 查 Redis 缓存（TTL=5分钟），命中则跳过数据库查询
      2. 缓存未命中：查主库 version_record，按 project + client_type 取 is_active=TRUE 记录
      3. 比较语义化版本号
      4. 返回 UpdateCheckResponse
    """
    record = await _get_active_version(
        client_type=client_type,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )

    if record is None:
        return UpdateCheckResponse(
            need_update=False,
            current_version="0.0.0",
            client_type=client_type,
            game_project_code=game_project_code,
        )

    server_version = record["version"]
    need_update = _version_gt(server_version, current_version)

    if not need_update:
        return UpdateCheckResponse(
            need_update=False,
            current_version=server_version,
            client_type=client_type,
            game_project_code=game_project_code,
        )

    return UpdateCheckResponse(
        need_update=True,
        current_version=server_version,
        client_type=client_type,
        game_project_code=game_project_code,
        force_update=record["force_update"],
        release_notes=record.get("release_notes"),
        checksum_sha256=record.get("checksum_sha256"),
    )


async def get_download_url(
    client_type: str,
    game_project_code: str,
    main_db: AsyncSession,
    redis,
) -> UpdateDownloadResponse:
    """生成限时签名下载 URL（有效期由 S3_URL_EXPIRE_SECONDS 控制，默认 10 分钟）。"""
    record = await _get_active_version(
        client_type=client_type,
        game_project_code=game_project_code,
        main_db=main_db,
        redis=redis,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"游戏 {game_project_code} 的 {client_type} 端暂无可用版本",
        )

    expire_seconds = settings.S3_URL_EXPIRE_SECONDS
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)

    storage = get_storage()
    download_url = await storage.get_download_url(
        path=record["package_path"],
        expire_seconds=expire_seconds,
    )

    return UpdateDownloadResponse(
        download_url=download_url,
        expires_at=expires_at,
        version=record["version"],
        checksum_sha256=record.get("checksum_sha256"),
    )


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_active_version(
    client_type: str,
    game_project_code: str,
    main_db: AsyncSession,
    redis,
) -> dict | None:
    """
    获取活跃版本信息，优先读 Redis 缓存，缓存未命中时查主库并写入缓存。
    返回 dict 或 None（无已发布版本）。

    V2 迁移后，VersionRecord 已从游戏库迁至主库，按 game_project_code 关联项目。
    """
    cache_key = _CACHE_KEY.format(
        game_project_code=game_project_code,
        client_type=client_type,
    )

    # 1. 尝试 Redis 缓存
    cached = await redis.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. 从主库查找项目 ID
    proj_result = await main_db.execute(
        select(GameProject).where(
            GameProject.code_name == game_project_code,
            GameProject.is_active == True,
        )
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        return None

    # 3. 查主库活跃版本
    result = await main_db.execute(
        select(VersionRecord).where(
            VersionRecord.game_project_id == project.id,
            VersionRecord.client_type == client_type,
            VersionRecord.is_active == True,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return None

    # 4. 序列化并写入 Redis 缓存
    data = {
        "id": record.id,
        "version": record.version,
        "package_path": record.package_path,
        "checksum_sha256": record.checksum_sha256,
        "release_notes": record.release_notes,
        "force_update": record.force_update,
        "released_at": record.released_at.isoformat() if record.released_at else None,
    }
    await redis.set(cache_key, json.dumps(data), ex=_CACHE_TTL)

    return data


def _version_gt(server: str, client: str) -> bool:
    """
    判断 server 版本号是否严格大于 client 版本号（语义化三段比较）。
    客户端版本格式非法时视为 0.0.0，始终触发更新。
    """
    def _parse(v: str) -> tuple[int, int, int]:
        try:
            parts = v.strip().split(".")
            if len(parts) != 3:
                raise ValueError
            return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            return (0, 0, 0)

    return _parse(server) > _parse(client)
