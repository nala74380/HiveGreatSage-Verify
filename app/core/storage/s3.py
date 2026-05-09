r"""
文件位置: app/core/storage/s3.py
名称: S3/MinIO/OSS 对象存储实现
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-09
版本: V2.0.0
功能说明:
    BaseStorage 的 S3 兼容对象存储实现。
    支持 AWS S3、MinIO 自建、阿里云 OSS 等所有 S3 兼容服务。

    通过 settings 配置:
      S3_ENDPOINT        — 对象存储端点（MinIO: http://minio:9000, OSS: https://oss-cn-xxx.aliyuncs.com）
      S3_BUCKET          — 存储桶名称
      S3_ACCESS_KEY      — Access Key
      S3_SECRET_KEY      — Secret Key
      S3_REGION          — 区域（默认 us-east-1）
      S3_URL_EXPIRE_SECONDS — Presigned URL 有效期

    设计要点:
      1. boto3 客户端在线程池中执行（boto3 是同步库）。
      2. save_file 适合小文件，save_file_from_path 适合大文件分块上传。
      3. get_download_url 生成 presigned URL，有效期可配置。
      4. 路径格式与 LocalStorage 一致：{game_code}/{client_type}/packages/{version}/{filename}

改进历史:
    V2.0.0 (2026-05-09) - 完整实现，支持 S3/MinIO/OSS；T004 决策已落地。
    V1.1.0 - 补齐 save_file_from_path 占位。
    V1.0.0 - 初始占位实现。
"""

import asyncio
import logging
from pathlib import Path

from app.config import settings
from app.core.storage.base import BaseStorage, FileNotFoundError, StorageError

logger = logging.getLogger(__name__)


class S3Storage(BaseStorage):
    """S3 兼容对象存储实现。"""

    def __init__(self) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        self._bucket = settings.S3_BUCKET

        if not self._bucket:
            raise StorageError("S3_BUCKET 未配置，拒绝初始化 S3 存储")

        logger.info(
            "S3 存储已初始化 | endpoint=%s bucket=%s region=%s",
            settings.S3_ENDPOINT or "AWS default",
            self._bucket,
            settings.S3_REGION,
        )

    async def save_file(self, data: bytes, path: str) -> str:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.put_object(
                    Bucket=self._bucket,
                    Key=path,
                    Body=data,
                ),
            )
        except Exception as e:
            raise StorageError(f"S3 保存文件失败：{path} — {e}") from e

        logger.info("S3 文件已保存: %s (%d bytes)", path, len(data))
        return path

    async def save_file_from_path(self, source_path: str | Path, path: str) -> str:
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"临时文件不存在：{src}")

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.upload_file(
                    str(src),
                    self._bucket,
                    path,
                ),
            )
        except Exception as e:
            raise StorageError(f"S3 上传文件失败：{path} — {e}") from e

        size = src.stat().st_size
        logger.info("S3 文件已上传: %s (%d bytes)", path, size)
        return path

    async def delete_file(self, path: str) -> None:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.delete_object(
                    Bucket=self._bucket,
                    Key=path,
                ),
            )
        except Exception as e:
            raise StorageError(f"S3 删除文件失败：{path} — {e}") from e

    async def get_download_url(
        self,
        path: str,
        expire_seconds: int = 600,
    ) -> str:
        try:
            url = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": path},
                    ExpiresIn=expire_seconds,
                ),
            )
            return url
        except Exception as e:
            raise StorageError(f"S3 生成下载 URL 失败：{path} — {e}") from e

    async def file_exists(self, path: str) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.head_object(
                    Bucket=self._bucket,
                    Key=path,
                ),
            )
            return True
        except Exception:
            return False

    async def get_file_size(self, path: str) -> int:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.head_object(
                    Bucket=self._bucket,
                    Key=path,
                ),
            )
            return int(response.get("ContentLength", 0))
        except Exception as e:
            raise FileNotFoundError(f"S3 文件不存在或无法获取大小：{path} — {e}") from e
