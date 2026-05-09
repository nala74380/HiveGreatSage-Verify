r"""
文件位置: app/core/storage/factory.py
名称: 存储实例工厂
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-09
版本: V2.0.0
功能说明:
    根据 settings.STORAGE_MODE 返回对应的存储实现单例。

用法：
    from app.core.storage import get_storage

    storage = get_storage()
    path = await storage.save_file(data, "game_001/android/packages/v1.0.1/xxx.lrj")
    url  = await storage.get_download_url(path, expire_seconds=600)

STORAGE_MODE 取值：
    "local" → LocalStorage（本地文件系统，默认）
    "s3"    → S3Storage（S3/MinIO/OSS，需配置 S3_* 环境变量）

改进历史:
    V2.0.0 (2026-05-09) - S3Storage 完整实现；S3 模式不再 fallback 到 local。
    V1.0.0 - 初始版本（S3 为占位实现，fallback 到 local）。
"""

import logging

from app.config import settings
from app.core.storage.base import BaseStorage

logger = logging.getLogger(__name__)

_storage_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage_instance

    if _storage_instance is not None:
        return _storage_instance

    mode = settings.STORAGE_MODE

    if mode == "s3":
        from app.core.storage.s3 import S3Storage

        _storage_instance = S3Storage()
        logger.info("存储模式: s3 | bucket=%s", settings.S3_BUCKET)
    else:
        from app.core.storage.local import LocalStorage

        _storage_instance = LocalStorage()
        logger.info("存储模式: local | 根目录=%s", settings.STORAGE_LOCAL_ROOT)

    return _storage_instance


def reset_storage_instance() -> None:
    global _storage_instance
    _storage_instance = None
