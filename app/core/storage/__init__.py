r"""
文件位置: app/core/storage/__init__.py
名称: 存储抽象层包入口
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    对外暴露统一的存储接口入口。
    其他模块只需导入此包，不直接依赖具体实现：
        from app.core.storage import get_storage, BaseStorage

改进历史:
    V1.0.0 - 初始版本
"""

from app.core.storage.base import BaseStorage
from app.core.storage.factory import get_storage

__all__ = ["BaseStorage", "get_storage"]
