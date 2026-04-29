r"""
文件位置: app/core/storage/s3.py
名称: S3/MinIO 对象存储实现（Phase 2 占位）
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    BaseStorage 的 S3/MinIO 对象存储实现（T004 决策后完善）。
    Phase 1 为占位实现，所有方法 fallback 到本地存储并记录警告日志。

    Phase 2 实现计划（T004 推演后补充）：
      - 选型确认：MinIO 自建 vs 云厂商 S3 兼容服务
      - 引入依赖：aiobotocore 或 boto3（同步包装到线程池）
      - 实现 save_file：boto3 put_object
      - 实现 get_download_url：boto3 generate_presigned_url
      - 实现 delete_file：boto3 delete_object
      - 实现 file_exists：boto3 head_object
      - 实现 get_file_size：boto3 head_object ContentLength

    配置项（settings）：
      S3_ENDPOINT   : MinIO 或 S3 兼容服务地址
      S3_BUCKET     : 存储桶名
      S3_ACCESS_KEY : 访问密钥
      S3_SECRET_KEY : 访问密钥 Secret
      S3_REGION     : 区域（S3 需要，MinIO 可任意值）
      S3_URL_EXPIRE_SECONDS : Presigned URL 有效期（默认 600s）

改进历史:
    V1.0.0 - 初始占位实现，等待 T004 存储选型决策后完善
调试信息:
    Phase 1 中 STORAGE_MODE=s3 时会记录 WARNING 并 fallback 到本地模式
"""

import logging

from app.core.storage.base import BaseStorage, StorageError

logger = logging.getLogger(__name__)

_S3_NOT_IMPLEMENTED_MSG = (
    "S3 存储尚未实现（等待 T004 对象存储选型决策），当前已 fallback 到本地模式。"
    "如需使用 S3，请完成 T004 推演后在此文件中实现相关方法。"
)


class S3Storage(BaseStorage):
    """
    S3/MinIO 对象存储实现（Phase 2 占位）。
    Phase 1 中所有方法均抛出 NotImplementedError，
    factory.py 中当 STORAGE_MODE=s3 时会记录警告并使用 LocalStorage 代替。
    """

    def __init__(self) -> None:
        logger.warning(
            "S3Storage 已初始化，但尚未实现（T004 待推演）。"
            "请勿在生产环境使用 STORAGE_MODE=s3，否则功能将不可用。"
        )

    async def save_file(self, data: bytes, path: str) -> str:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED_MSG)

    async def delete_file(self, path: str) -> None:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED_MSG)

    async def get_download_url(
        self,
        path: str,
        expire_seconds: int = 600,
    ) -> str:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED_MSG)

    async def file_exists(self, path: str) -> bool:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED_MSG)

    async def get_file_size(self, path: str) -> int:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED_MSG)

    # ── Phase 2 实现模板（T004 推演后取消注释并实现）───────────
    #
    # def __init__(self) -> None:
    #     import boto3
    #     self._client = boto3.client(
    #         "s3",
    #         endpoint_url=settings.S3_ENDPOINT,
    #         aws_access_key_id=settings.S3_ACCESS_KEY,
    #         aws_secret_access_key=settings.S3_SECRET_KEY,
    #         region_name=settings.S3_REGION,
    #     )
    #     self._bucket = settings.S3_BUCKET
    #
    # async def save_file(self, data: bytes, path: str) -> str:
    #     await asyncio.get_event_loop().run_in_executor(
    #         None,
    #         lambda: self._client.put_object(
    #             Bucket=self._bucket, Key=path, Body=data
    #         )
    #     )
    #     return path
    #
    # async def get_download_url(self, path: str, expire_seconds: int = 600) -> str:
    #     url = await asyncio.get_event_loop().run_in_executor(
    #         None,
    #         lambda: self._client.generate_presigned_url(
    #             "get_object",
    #             Params={"Bucket": self._bucket, "Key": path},
    #             ExpiresIn=expire_seconds,
    #         )
    #     )
    #     return url
