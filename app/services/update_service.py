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

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.request_context import get_request_id
from app.core.storage import get_storage
from app.core.utils import get_project_or_404
from app.models.main.models import Admin, GameProject, VersionRecord
from app.schemas.update import (
    UpdateCheckResponse,
    UpdateDownloadResponse,
)
from app.services.audit_service import create_audit_log

_CACHE_KEY = "update:latest:{game_project_code}:{client_type}"
_CACHE_TTL = 300  # 5 分钟
_ALLOWED_EXTENSIONS_BY_CLIENT = {
    "android": {".lrj", ".apk"},
    "pc": {".zip", ".exe"},
}
_MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def publish_version_package(
    *,
    project_id: int,
    client_type: Literal["pc", "android"],
    version: str,
    force_update: bool,
    release_notes: str | None,
    file: UploadFile,
    current_admin: Admin,
    db: AsyncSession,
    redis,
) -> dict:
    """管理员上传并发布热更新包。"""
    project = await get_project_or_404(project_id, db)

    if not file.filename:
        raise HTTPException(status_code=422, detail="文件名不能为空")

    original_filename = _safe_filename(file.filename)
    ext = "." + original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    allowed_extensions = _ALLOWED_EXTENSIONS_BY_CLIENT[client_type]
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的 {client_type} 包格式 '{ext}'，允许：{', '.join(sorted(allowed_extensions))}",
        )

    request_id = get_request_id()
    temp_path, checksum, file_size = await _write_upload_to_temp_file(file)
    package_path = f"{project.code_name}/{client_type}/packages/{version}/{original_filename}"
    storage = get_storage()
    saved_path: str | None = None

    try:
        saved_path = await storage.save_file_from_path(source_path=temp_path, path=package_path)

        existing_result = await db.execute(
            select(VersionRecord).where(
                VersionRecord.game_project_id == project_id,
                VersionRecord.client_type == client_type,
                VersionRecord.version == version,
            )
        )
        existing = existing_result.scalar_one_or_none()
        is_republish = existing is not None

        await db.execute(
            update(VersionRecord)
            .where(
                VersionRecord.game_project_id == project_id,
                VersionRecord.client_type == client_type,
                VersionRecord.is_active == True,
            )
            .values(is_active=False)
        )

        if existing:
            existing.package_path = saved_path
            existing.checksum_sha256 = checksum
            existing.release_notes = release_notes
            existing.force_update = force_update
            existing.is_active = True
            existing.released_at = datetime.now(timezone.utc)
            existing.released_by_admin_id = current_admin.id
            existing.original_filename = original_filename
            existing.file_size = file_size
            existing.request_id = request_id
            await db.flush()
            record = existing
            message = f"版本 {version} 已重新发布"
        else:
            record = VersionRecord(
                game_project_id=project_id,
                client_type=client_type,
                version=version,
                package_path=saved_path,
                checksum_sha256=checksum,
                release_notes=release_notes,
                force_update=force_update,
                is_active=True,
                released_by_admin_id=current_admin.id,
                original_filename=original_filename,
                file_size=file_size,
                request_id=request_id,
            )
            db.add(record)
            await db.flush()
            message = f"版本 {version} 发布成功"

        await create_audit_log(
            db=db,
            actor_type="admin",
            actor_id=current_admin.id,
            action="update.publish",
            target_type="version_record",
            target_id=record.id,
            summary=f"发布热更新 {project.code_name}/{client_type} v{version}",
            metadata={
                "game_project_id": project.id,
                "game_project_code": project.code_name,
                "client_type": client_type,
                "version": version,
                "force_update": force_update,
                "is_republish": is_republish,
                "original_filename": original_filename,
                "file_size": file_size,
                "checksum_sha256": checksum,
                "package_path": saved_path,
            },
            request_id=request_id,
        )

        cache_key = _CACHE_KEY.format(
            game_project_code=project.code_name,
            client_type=client_type,
        )
        await redis.delete(cache_key)

        return {**_record_to_dict(record, project.code_name), "message": message}
    except Exception:
        if saved_path:
            try:
                await storage.delete_file(saved_path)
            except Exception:
                pass
        raise
    finally:
        if temp_path.exists():
            temp_path.unlink()


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

def _record_to_dict(record: VersionRecord, project_code: str) -> dict:
    return {
        "id": record.id,
        "version": record.version,
        "client_type": record.client_type,
        "force_update": record.force_update,
        "release_notes": record.release_notes,
        "checksum_sha256": record.checksum_sha256,
        "package_path": record.package_path,
        "released_at": record.released_at.isoformat() if record.released_at else None,
        "released_by_admin_id": record.released_by_admin_id,
        "original_filename": record.original_filename,
        "file_size": record.file_size,
        "request_id": record.request_id,
        "is_active": record.is_active,
        "game_project_code": project_code,
    }


def _safe_filename(filename: str) -> str:
    """只保留上传文件名本身，避免路径穿越。"""
    return Path(filename).name


async def _write_upload_to_temp_file(file: UploadFile) -> tuple[Path, str, int]:
    """
    分块读取 UploadFile 到本地临时文件，同时计算 SHA-256。

    Returns:
        temp_path, checksum_sha256, total_size

    Raises:
        HTTPException: 文件为空或超过大小限制。
    """
    hasher = hashlib.sha256()
    total_size = 0
    fd, temp_name = tempfile.mkstemp(prefix="hgs_update_", suffix=".upload")
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "wb") as tmp:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > _MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="文件超出 500 MB 限制")

                hasher.update(chunk)
                tmp.write(chunk)

            tmp.flush()
            os.fsync(tmp.fileno())

        if total_size <= 0:
            raise HTTPException(status_code=422, detail="文件内容为空")

        return temp_path, hasher.hexdigest(), total_size
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


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
