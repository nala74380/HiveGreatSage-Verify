r"""
文件位置: app/core/storage/local.py
名称: 本地文件系统存储实现
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    BaseStorage 的本地文件系统实现。
    适用于家庭 VPS 自建部署场景（D006 模式 A）。

    文件存储根目录由 settings.STORAGE_LOCAL_ROOT 指定，
    默认 /var/www/hive-updates（由 nginx 提供静态文件服务）。

    目录结构：
      {STORAGE_LOCAL_ROOT}/
        game_001/
          android/
            packages/
              v1.0.1/
                game_001_android_v1.0.1.lrj
          pc/
            packages/
              v1.0.1/
                game_001_pc_v1.0.1.zip

    下载 URL 生成（本地模式）：
      https://{domain}/updates/{path}?token={signed_jwt}
      nginx 配置 /updates/ location 指向 STORAGE_LOCAL_ROOT。
      token 用于安全验证（Phase 1 可选，Phase 2 建议配置 nginx auth_request）。

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: Windows 路径与 Linux 路径分隔符需注意，使用 pathlib.Path 统一处理
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import jwt

from app.config import settings
from app.core.storage.base import BaseStorage, FileNotFoundError, StorageError

logger = logging.getLogger(__name__)

_DOWNLOAD_TOKEN_ALGORITHM = "HS256"


class LocalStorage(BaseStorage):
    """
    本地文件系统存储实现。
    所有文件操作基于 settings.STORAGE_LOCAL_ROOT 根目录。
    """

    def __init__(self) -> None:
        self._root = Path(settings.STORAGE_LOCAL_ROOT)
        # 确保根目录存在（启动时自动创建）
        self._root.mkdir(parents=True, exist_ok=True)

    def _abs_path(self, relative_path: str) -> Path:
        """将相对路径转换为绝对路径，防止路径穿越攻击。"""
        abs_path = (self._root / relative_path).resolve()
        # 安全检查：确保路径在根目录内
        if not str(abs_path).startswith(str(self._root.resolve())):
            raise StorageError(f"非法路径：{relative_path}")
        return abs_path

    async def save_file(self, data: bytes, path: str) -> str:
        """
        保存文件到本地文件系统。
        自动创建中间目录（parents=True）。
        """
        abs_path = self._abs_path(path)
        try:
            # 在线程池中执行同步 IO，不阻塞事件循环
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._sync_write,
                abs_path,
                data,
            )
        except OSError as e:
            raise StorageError(f"保存文件失败：{path} — {e}") from e

        logger.info("文件已保存: %s (%d bytes)", path, len(data))
        return path

    async def delete_file(self, path: str) -> None:
        """删除本地文件，文件不存在时静默忽略。"""
        abs_path = self._abs_path(path)
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._sync_delete,
                abs_path,
            )
        except OSError as e:
            raise StorageError(f"删除文件失败：{path} — {e}") from e

    async def get_download_url(
        self,
        path: str,
        expire_seconds: int = 600,
    ) -> str:
        """
        生成本地存储的签名下载 URL。
        URL 格式：https://{domain}/updates/{path}?token={signed_jwt}

        token payload：
          type=download_token, path=path, exp=expire_at
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expire_seconds)

        payload = {
            "type": "download_token",
            "path": path,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm=_DOWNLOAD_TOKEN_ALGORITHM,
        )
        # path 中的反斜杠统一转为正斜杠（Windows 兼容）
        url_path = path.replace("\\", "/")
        return f"https://{settings.DOMAIN}/updates/{url_path}?token={token}"

    async def file_exists(self, path: str) -> bool:
        """检查本地文件是否存在。"""
        abs_path = self._abs_path(path)
        return await asyncio.get_event_loop().run_in_executor(
            None,
            abs_path.exists,
        )

    async def get_file_size(self, path: str) -> int:
        """获取本地文件大小（字节）。"""
        abs_path = self._abs_path(path)
        if not abs_path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")
        stat = await asyncio.get_event_loop().run_in_executor(
            None,
            abs_path.stat,
        )
        return stat.st_size

    # ── 同步辅助（在线程池中执行）──────────────────────────────

    @staticmethod
    def _sync_write(abs_path: Path, data: bytes) -> None:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)

    @staticmethod
    def _sync_delete(abs_path: Path) -> None:
        if abs_path.exists():
            abs_path.unlink()


def compute_sha256(data: bytes) -> str:
    """计算文件 SHA-256 校验值（用于上传时自动计算 checksum）。"""
    return hashlib.sha256(data).hexdigest()
