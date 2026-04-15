from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "HiveGreatSage-Verify"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/hive_platform"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_HOURS: int = 2
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    STORAGE_MODE: str = "local"
    STORAGE_LOCAL_ROOT: str = "/var/www/hive-updates"
    S3_ENDPOINT: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
