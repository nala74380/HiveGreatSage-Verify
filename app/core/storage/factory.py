r"""
文件位置: app/core/storage/factory.py
名称: 存储实例工厂
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    根据 settings.STORAGE_MODE 返回对应的存储实现单例。

    用法：
        from app.core.storage import get_storage

        storage = get_storage()
        path = await storage.save_file(data, "game_001/android/packages/v1.0.1/xxx.lrj")
        url  = await storage.get_download_url(path, expire_seconds=600)

    单例模式：
        get_storage() 返回的是模块级缓存实例，整个应用生命周期只创建一次。
        如需在测试中替换存储实现，可直接替换 _storage_instance。

    STORAGE_MODE 取值：
        "local" → LocalStorage（本地文件系统，Phase 1 默认）
        "s3"    → S3Storage（对象存储，Phase 2 实现后启用）
                  当前 S3Storage 未实现，会记录 WARNING 并 fallback 到 local。

改进历史:
    V1.0.0 - 初始版本
"""

import logging

from app.config import settings
from app.core.storage.base import BaseStorage

logger = logging.getLogger(__name__)

# 模块级单例缓存
_storage_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    """
    获取存储实现单例。

    根据 settings.STORAGE_MODE 决定使用哪种存储后端：
      "local" → LocalStorage
      "s3"    → S3Storage（Phase 2 前 fallback 到 LocalStorage）
    """
    global _storage_instance

    if _storage_instance is not None:
        return _storage_instance

    mode = settings.STORAGE_MODE

    if mode == "s3":
        try:
            from app.core.storage.s3 import S3Storage
            # 尝试初始化 S3Storage，如果抛出 NotImplementedError 则 fallback
            instance = S3Storage()
            logger.warning(
                "STORAGE_MODE=s3 但 S3Storage 尚未完整实现（T004 待推演），"
                "已 fallback 到 LocalStorage。生产环境请完成 T004 后再启用 S3 模式。"
            )
            from app.core.storage.local import LocalStorage
            _storage_instance = LocalStorage()
        except Exception as e:
            logger.error("S3Storage 初始化失败: %s，fallback 到 LocalStorage", e)
            from app.core.storage.local import LocalStorage
            _storage_instance = LocalStorage()
    else:
        # 默认 local 模式
        from app.core.storage.local import LocalStorage
        _storage_instance = LocalStorage()
        logger.info(
            "存储模式: local | 根目录: %s", settings.STORAGE_LOCAL_ROOT
        )

    return _storage_instance


def reset_storage_instance() -> None:
    """
    重置存储单例（仅用于测试）。
    在测试 teardown 时调用，确保各测试用例使用独立的存储实例。
    """
    global _storage_instance
    _storage_instance = None
