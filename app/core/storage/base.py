r"""
文件位置: app/core/storage/base.py
名称: 存储抽象基类
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    定义存储层的统一抽象接口（Abstract Base Class）。
    LocalStorage 和 S3Storage 均继承此类并实现全部抽象方法。

    设计原则（D010 决策）：
      调用方（如 update_service.py）只依赖 BaseStorage 接口，
      不感知底层是本地文件系统还是对象存储。
      通过 factory.get_storage() 获取实例，由配置决定具体实现。

    接口说明：
      save_file(data, path)   → 保存文件，返回存储路径（相对路径）
      delete_file(path)       → 删除文件
      get_download_url(path, expire_seconds)  → 生成限时下载 URL
      file_exists(path)       → 检查文件是否存在
      get_file_size(path)     → 获取文件大小（字节）

    path 约定（两种模式统一）：
      相对路径格式：{game_code}/{client_type}/packages/{version}/{filename}
      例如：game_001/android/packages/v1.0.1/game_001_android_v1.0.1.lrj

改进历史:
    V1.0.0 - 初始版本
"""

from abc import ABC, abstractmethod


class BaseStorage(ABC):
    """存储层抽象基类，定义统一的文件操作接口。"""

    @abstractmethod
    async def save_file(
        self,
        data: bytes,
        path: str,
    ) -> str:
        """
        保存文件到存储后端。

        Args:
            data: 文件二进制内容
            path: 存储路径（相对路径，不含存储根目录前缀）
                  格式：{game_code}/{client_type}/packages/{version}/{filename}

        Returns:
            str: 存储路径（与传入 path 一致，供写入数据库使用）

        Raises:
            StorageError: 保存失败时抛出
        """
        ...

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """
        删除存储中的文件。

        Args:
            path: 文件的相对存储路径

        Raises:
            StorageError: 删除失败时抛出（文件不存在时静默忽略）
        """
        ...

    @abstractmethod
    async def get_download_url(
        self,
        path: str,
        expire_seconds: int = 600,
    ) -> str:
        """
        生成文件的限时下载 URL。

        本地模式：生成带签名 JWT 的静态文件 URL
          https://{domain}/updates/{path}?token={signed_jwt}

        S3 模式：生成 Presigned URL，客户端直接访问对象存储

        Args:
            path: 文件的相对存储路径
            expire_seconds: URL 有效期（秒），默认 600 秒（10 分钟）

        Returns:
            str: 带签名的限时下载 URL
        """
        ...

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """
        检查文件是否存在。

        Args:
            path: 文件的相对存储路径

        Returns:
            bool: 文件存在返回 True，否则 False
        """
        ...

    @abstractmethod
    async def get_file_size(self, path: str) -> int:
        """
        获取文件大小。

        Args:
            path: 文件的相对存储路径

        Returns:
            int: 文件大小（字节）

        Raises:
            StorageError: 文件不存在时抛出
        """
        ...


class StorageError(Exception):
    """存储操作异常基类。"""
    pass


class FileNotFoundError(StorageError):
    """文件不存在异常。"""
    pass


class StoragePermissionError(StorageError):
    """存储权限异常。"""
    pass
