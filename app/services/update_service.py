r"""
文件位置: app/services/update_service.py
文件名称: update_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.1
功能说明:
    热更新服务层，包含全部业务逻辑：
      - check_update()      检查版本、比较、返回是否需要更新
      - get_download_url()  生成带签名的限时下载 URL
      - upload_version()    发布新版本（C06，管理员调用）
      - invalidate_version_cache()  主动删除版本 Redis 缓存

    版本比较规则：
      只比较 MAJOR.MINOR.PATCH 三段，任意一段服务端更大则触发更新。
      客户端版本 >= 服务端版本：无需更新（need_update=False）。
      客户端版本格式非法时：视为 0.0.0，强制触发更新。

    Redis 缓存策略：
      Key: update:latest:{game_project_code}:{client_type}
      TTL: 300 秒（5 分钟）
      发布新版本时主动删除缓存（invalidate_version_cache）。

    upload_version 发布流程（C06）：
      1. 计算文件 SHA-256 校验值
      2. 调用存储抽象层（LocalStorage / S3Storage）保存文件
      3. 将旧活跃版本 is_active 置为 FALSE（归档）
      4. 插入新版本记录（is_active=TRUE）
      5. 主动删除 Redis 缓存，确保下次 check_update 读到最新版本

关联文档:
    [[01-网络验证系统/架构设计]] 第十节 热更新机制
    [[01-网络验证系统/数据库设计]] 3.5 version_record

改进历史:
    V1.0.1 (2026-04-25) - 新增 upload_version()（C06），迁移 _build_local_url 到存储抽象层
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.storage import get_storage
from app.core.storage.local import compute_sha256
from app.models.game.models import VersionRecord
from app.schemas.update import (
    UpdateCheckResponse,
    UpdateDownloadResponse,
    VersionUploadRequest,
    VersionUploadResponse,
)

logger = logging.getLogger(__name__)

# Redis cache key 模板
_CACHE_KEY = "update:latest:{game_project_code}:{client_type}"
_CACHE_TTL = 300   # 5 分钟


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def check_update(
    current_version: str,
    client_type: str,
    game_project_code: str,
    game_db: AsyncSession,
    redis,
) -> UpdateCheckResponse:
    """
    检查是否有新版本。

    流程：
      1. 查 Redis 缓存（TTL=5分钟），命中则跳过数据库查询
      2. 缓存未命中：查游戏库 version_record，取 is_active=TRUE 的记录
      3. 比较语义化版本号
      4. 返回 UpdateCheckResponse
    """
    record = await _get_active_version(
        client_type=client_type,
        game_project_code=game_project_code,
        game_db=game_db,
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
    game_db: AsyncSession,
    redis,
) -> UpdateDownloadResponse:
    """生成限时签名下载 URL（有效期由 S3_URL_EXPIRE_SECONDS 控制，默认 10 分钟）。"""
    record = await _get_active_version(
        client_type=client_type,
        game_project_code=game_project_code,
        game_db=game_db,
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


async def upload_version(
    file_data: bytes,
    filename: str,
    meta: VersionUploadRequest,
    game_project_code: str,
    game_db: AsyncSession,
    redis,
) -> VersionUploadResponse:
    """
    发布新版本（C06，管理员调用）。

    完整流程：
      1. 计算文件 SHA-256 校验值
      2. 构建存储路径：{game_code}/{client_type}/packages/{version}/{filename}
      3. 调用存储抽象层保存文件（LocalStorage 或 S3Storage）
      4. 将旧活跃版本 is_active 置为 FALSE（归档，不删除历史记录）
      5. 插入新版本记录（is_active=TRUE）
      6. 主动删除 Redis 缓存，确保下次 check_update 立即读到新版本
      7. 返回新版本信息

    幂等性说明：
      同一 game_project_code + client_type + version 的包重复上传时：
      - 文件会被覆盖（存储层）
      - version_record 不会重复插入（version + client_type 唯一）
      - 若旧记录已存在，更新 package_path / checksum / release_notes
    """
    # Step 1: 计算 SHA-256
    checksum = compute_sha256(file_data)

    # Step 2: 构建存储路径
    package_path = (
        f"{game_project_code}/{meta.client_type}/packages/"
        f"{meta.version}/{filename}"
    )

    # Step 3: 保存文件
    storage = get_storage()
    saved_path = await storage.save_file(data=file_data, path=package_path)
    logger.info(
        "热更新包已保存: game=%s client=%s version=%s path=%s size=%d bytes",
        game_project_code, meta.client_type, meta.version, saved_path, len(file_data),
    )

    # Step 4: 归档旧活跃版本
    await game_db.execute(
        update(VersionRecord)
        .where(
            VersionRecord.client_type == meta.client_type,
            VersionRecord.is_active == True,
        )
        .values(is_active=False)
    )

    # Step 5: 检查同版本记录是否已存在（幂等处理）
    existing_result = await game_db.execute(
        select(VersionRecord).where(
            VersionRecord.version == meta.version,
            VersionRecord.client_type == meta.client_type,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # 同版本重新上传：更新字段，重新激活
        existing.package_path = saved_path
        existing.checksum_sha256 = checksum
        existing.release_notes = meta.release_notes
        existing.force_update = meta.force_update
        existing.is_active = True
        existing.released_at = datetime.now(timezone.utc)
        await game_db.flush()
        record = existing
        op_msg = f"版本 {meta.version} 已重新发布（覆盖旧包），旧版本已归档"
    else:
        # 插入全新版本记录
        record = VersionRecord(
            client_type=meta.client_type,
            version=meta.version,
            package_path=saved_path,
            checksum_sha256=checksum,
            release_notes=meta.release_notes,
            force_update=meta.force_update,
            is_active=True,
        )
        game_db.add(record)
        await game_db.flush()
        op_msg = f"版本 {meta.version} 发布成功，旧版本已归档"

    # Step 6: 主动删除 Redis 缓存
    await invalidate_version_cache(
        game_project_code=game_project_code,
        client_type=meta.client_type,
        redis=redis,
    )

    logger.info(
        "热更新版本发布完成: game=%s client=%s version=%s force=%s",
        game_project_code, meta.client_type, meta.version, meta.force_update,
    )

    return VersionUploadResponse(
        id=record.id,
        version=record.version,
        client_type=record.client_type,
        package_path=record.package_path,
        checksum_sha256=checksum,
        force_update=record.force_update,
        release_notes=record.release_notes,
        released_at=record.released_at,
        game_project_code=game_project_code,
        message=op_msg,
    )


async def invalidate_version_cache(
    game_project_code: str,
    client_type: str,
    redis,
) -> None:
    """主动删除版本缓存（发布新版本时调用）。"""
    cache_key = _CACHE_KEY.format(
        game_project_code=game_project_code,
        client_type=client_type,
    )
    await redis.delete(cache_key)
    logger.info("版本缓存已清除: game=%s client=%s", game_project_code, client_type)


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

async def _get_active_version(
    client_type: str,
    game_project_code: str,
    game_db: AsyncSession,
    redis,
) -> dict | None:
    """
    获取活跃版本信息，优先读 Redis 缓存，缓存未命中时查数据库并写入缓存。
    返回 dict 或 None（无已发布版本）。
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

    # 2. 查游戏数据库
    result = await game_db.execute(
        select(VersionRecord).where(
            VersionRecord.client_type == client_type,
            VersionRecord.is_active == True,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return None

    # 3. 序列化并写入 Redis 缓存
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
