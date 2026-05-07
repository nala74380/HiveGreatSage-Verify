r"""
文件位置: app/routers/update_admin.py
名称: 热更新管理路由（管理员专用）
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-07
版本: V2.4.0
功能说明:
    POST   /admin/api/updates/{project_id}/{client_type}         上传并发布热更新包
    GET    /admin/api/updates/{project_id}/{client_type}/latest  获取当前活跃版本
    GET    /admin/api/updates/{project_id}/{client_type}/history 获取版本历史

    V2 改动：版本记录从游戏库迁移到主库（version_record 表），
    兼容游戏项目和普通验证项目，不再需要连接游戏库。

当前上传口径:
    - 禁止 await file.read() 一次性读取大文件。
    - 上传包先分块写入临时文件，同时计算 SHA-256。
    - 超过 500MB 立即中止并清理临时文件。
    - 临时文件写完后交给存储层 save_file_from_path() 原子落盘。
    - 数据库写入失败时尝试删除已保存文件，避免孤儿包。
    - VersionRecord 记录发布管理员、原始文件名、文件大小和 request_id。
    - 发布成功后写入 audit_log。

改进内容:
    V2.4.0 (2026-05-07) - 热更新发布接入 audit_log
    V2.3.0 (2026-05-07) - request_id 改为从 RequestIdMiddleware 上下文读取
    V2.2.0 (2026-05-07) - VersionRecord 写入发布审计字段
    V2.1.0 (2026-05-07) - 上传包改为流式读取 + 临时文件 + 原子落盘
    V2.0.0 (2026-04-26) - 版本记录改存主库，支持验证项目热更新
    V1.0.0 - 初始版本（仅支持游戏项目）
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.redis_client import get_redis
from app.core.request_context import get_request_id
from app.core.storage import get_storage
from app.database import get_main_db
from app.models.main.models import Admin, GameProject, VersionRecord
from app.services.audit_service import create_audit_log

router = APIRouter()

_ALLOWED_EXTENSIONS_BY_CLIENT = {
    "android": {".lrj", ".apk"},
    "pc": {".zip", ".exe"},
}
_MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


from app.core.utils import get_project_or_404 as _get_project_or_404


def _record_to_dict(r: VersionRecord, project_code: str) -> dict:
    return {
        "id":              r.id,
        "version":         r.version,
        "client_type":     r.client_type,
        "force_update":    r.force_update,
        "release_notes":   r.release_notes,
        "checksum_sha256": r.checksum_sha256,
        "package_path":    r.package_path,
        "released_at":     r.released_at.isoformat() if r.released_at else None,
        "released_by_admin_id": r.released_by_admin_id,
        "original_filename": r.original_filename,
        "file_size": r.file_size,
        "request_id": r.request_id,
        "is_active":       r.is_active,
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


# ── 上传发布 ──────────────────────────────────────────────────

@router.post(
    "/{project_id}/{client_type}",
    status_code=201,
    summary="发布热更新包",
)
async def upload_version_endpoint(
    project_id: int,
    client_type: Literal["pc", "android"],
    version: str = Form(..., pattern=r"^\d+\.\d+\.\d+$"),
    force_update: bool = Form(default=False),
    release_notes: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    发布热更新包（管理员专用，multipart/form-data）。
    支持游戏项目和普通验证项目。
    """
    project = await _get_project_or_404(project_id, db)

    # 校验文件扩展名
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

        # 幂等：先查同版本，再归档旧活跃版本。
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
            msg = f"版本 {version} 已重新发布"
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
            msg = f"版本 {version} 发布成功"

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

        # 主动清除 Redis 版本缓存（game 项目的客户端检查缓存）
        cache_key = f"update:latest:{project.code_name}:{client_type}"
        await redis.delete(cache_key)

        return {**_record_to_dict(record, project.code_name), "message": msg}
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


# ── 查询 ──────────────────────────────────────────────────────

@router.get("/{project_id}/{client_type}/latest", summary="获取当前活跃版本")
async def get_latest_version(
    project_id: int,
    client_type: Literal["pc", "android"],
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    project = await _get_project_or_404(project_id, db)
    result = await db.execute(
        select(VersionRecord).where(
            VersionRecord.game_project_id == project_id,
            VersionRecord.client_type == client_type,
            VersionRecord.is_active == True,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail=f"尚未发布 {client_type} 端版本")
    return _record_to_dict(record, project.code_name)


@router.get("/{project_id}/{client_type}/history", summary="版本历史")
async def get_version_history(
    project_id: int,
    client_type: Literal["pc", "android"],
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    project = await _get_project_or_404(project_id, db)
    result = await db.execute(
        select(VersionRecord)
        .where(
            VersionRecord.game_project_id == project_id,
            VersionRecord.client_type == client_type,
        )
        .order_by(VersionRecord.released_at.desc())
    )
    records = result.scalars().all()
    return {"versions": [_record_to_dict(r, project.code_name) for r in records]}
