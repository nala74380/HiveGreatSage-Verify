r"""
文件位置: app/config.py
文件名称: config.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.1
功能说明:
    所有配置的唯一入口。通过 Pydantic BaseSettings 从环境变量或 .env 文件读取。
    代码中任何地方需要配置，都从这里导入 settings，绝不硬编码任何值。
    用法：from app.config import settings
改进历史:
    v1.0.1 (2026-04-25) - 新增 TIMEZONE 字段，默认 Asia/Shanghai (UTC+8)
调试信息: 启动时若缺少必填字段（如 SECRET_KEY）会直接抛出 ValidationError。
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── 基础 ──────────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "production"] = "development"
    SECRET_KEY: str                          # 必填，无默认值，启动时强制检查
    DEBUG: bool = False

    # ── Token 有效期（v3 架构设计锁定：AT=15min / RT=7天）─────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # 管理员/代理 Token 有效期（浏览器窗口会话，默认 8 小时）
    ADMIN_TOKEN_EXPIRE_HOURS: int = 8
    AGENT_TOKEN_EXPIRE_HOURS: int = 8

    # ── 时区 ──────────────────────────────────────────────────
    # 默认 Asia/Shanghai（UTC+8），影响：日志时间戳、API 响应时间展示
    # 数据库始终以 UTC 存储，仅在展示层转换
    TIMEZONE: str = "Asia/Shanghai"

    # ── 数据库 ────────────────────────────────────────────────
    # 主库（用户管理，固定名称 hive_platform）
    DATABASE_MAIN_URL: str = (
        "postgresql+asyncpg://hive_user:password@localhost:5432/hive_platform"
    )
    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── 网络 ──────────────────────────────────────────────────
    DOMAIN: str = "localhost"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        """将逗号分隔的字符串转为列表，供 CORS 中间件使用。"""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── 文件存储 ──────────────────────────────────────────────
    STORAGE_MODE: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_ROOT: str = "/var/www/hive-updates"

    # S3 / MinIO（STORAGE_MODE=s3 时必填）
    S3_ENDPOINT: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_REGION: str = "us-east-1"
    S3_URL_EXPIRE_SECONDS: int = 600        # 签名下载 URL 有效期：10 分钟

    # ── 日志与监控（D6 决策）──────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    SQLALCHEMY_LOG_LEVEL: str = "WARNING"   # WARNING=屏蔽 SQL 语句，DEBUG=显示全部 SQL
    SENTRY_DSN: str = ""                    # 空字符串表示不启用

    # ── 验证：生产环境必须显式关闭 DEBUG ─────────────────────
    @field_validator("DEBUG")
    @classmethod
    def debug_must_be_false_in_production(cls, v: bool, info) -> bool:
        if v and info.data.get("ENVIRONMENT") == "production":
            raise ValueError("生产环境 DEBUG 必须为 False")
        return v


@lru_cache
def get_settings() -> Settings:
    """
    返回 Settings 单例（lru_cache 保证全程只解析一次 .env）。
    测试时可用 app.config.get_settings.cache_clear() 重置。
    """
    return Settings()


# 全局单例，全项目通过 `from app.config import settings` 导入
settings: Settings = get_settings()
