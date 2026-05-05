r"""
文件位置: app/routers/update_admin.py
名称: 热更新管理路由（管理员专用）
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-26
版本: V2.0.0
功能说明:
    POST   /admin/api/updates/{project_id}/{client_type}         上传并发布热更新包
    GET    /admin/api/updates/{project_id}/{client_type}/latest  获取当前活跃版本
    GET    /admin/api/updates/{project_id}/{client_type}/history 获取版本历史

    V2 改动：版本记录从游戏库迁移到主库（version_record 表），
    兼容游戏项目和普通验证项目，不再需要连接游戏库。

改进内容:
    V2.0.0 (2026-04-26) - 版本记录改存主库，支持验证项目热更新
    V1.0.0 - 初始版本（仅支持游戏项目）
调试信息:
    已知问题: 无
"""

from typing import Literal
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.redis_client import get_redis
from app.core.storage import get_storage
from app.core.storage.local import compute_sha256
from app.database import get_main_db
from app.models.main.models import Admin, GameProject, VersionRecord

router = APIRouter()

_ALLOWED_EXTENSIONS_BY_CLIENT = {
    "android": {".lrj", ".apk"},
    "pc": {".zip", ".exe"},
}
_MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


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
        "is_active":       r.is_active,
        "game_project_code": project_code,
    }


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
    _: Admin = Depends(get_current_admin),
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
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed_extensions = _ALLOWED_EXTENSIONS_BY_CLIENT[client_type]
    if ext not in allowed_extensions:
        raise HTTPException(status_code=422,
                            detail=f"不支持的 {client_type} 包格式 '{ext}'，允许：{', '.join(sorted(allowed_extensions))}")

    file_data = await file.read()
    if not file_data:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(file_data) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件超出 500 MB 限制")

    # 计算校验值 + 保存文件
    checksum = compute_sha256(file_data)
    package_path = f"{project.code_name}/{client_type}/packages/{version}/{file.filename}"
    storage = get_storage()
    saved_path = await storage.save_file(data=file_data, path=package_path)

    # 归档旧活跃版本
    await db.execute(
        update(VersionRecord)
        .where(
            VersionRecord.game_project_id == project_id,
            VersionRecord.client_type == client_type,
            VersionRecord.is_active == True,
        )
        .values(is_active=False)
    )

    # 幂等：同版本重复上传则更新
    existing_result = await db.execute(
        select(VersionRecord).where(
            VersionRecord.game_project_id == project_id,
            VersionRecord.client_type == client_type,
            VersionRecord.version == version,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.package_path    = saved_path
        existing.checksum_sha256 = checksum
        existing.release_notes   = release_notes
        existing.force_update    = force_update
        existing.is_active       = True
        existing.released_at     = datetime.now(timezone.utc)
        await db.flush()
        record = existing
        msg = f"版本 {version} 已重新发布"
    else:
        record = VersionRecord(
            game_project_id = project_id,
            client_type     = client_type,
            version         = version,
            package_path    = saved_path,
            checksum_sha256 = checksum,
            release_notes   = release_notes,
            force_update    = force_update,
            is_active       = True,
        )
        db.add(record)
        await db.flush()
        msg = f"版本 {version} 发布成功"

    # 主动清除 Redis 版本缓存（game 项目的客户端检查缓存）
    cache_key = f"update:latest:{project.code_name}:{client_type}"
    await redis.delete(cache_key)

    return {**_record_to_dict(record, project.code_name), "message": msg}


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
