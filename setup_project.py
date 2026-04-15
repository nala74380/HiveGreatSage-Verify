#!/usr/bin/env python3
"""
项目骨架生成脚本
运行后将创建 HiveGreatSage-Verify 的完整目录结构和占位文件。
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()

DIRECTORIES = [
    "app",
    "app/models",
    "app/models/main",
    "app/models/game",
    "app/routers",
    "app/services",
    "app/repositories",
    "app/schemas",
    "app/core",
    "app/core/storage",
    "app/tasks",
    "migrations",
    "migrations/versions",
    "frontend",
    "tests",
    "tests/unit",
    "tests/integration",
    "deploy",
    "deploy/systemd",
]

PY_PACKAGES = [
    "app",
    "app/models",
    "app/models/main",
    "app/models/game",
    "app/routers",
    "app/services",
    "app/repositories",
    "app/schemas",
    "app/core",
    "app/core/storage",
    "app/tasks",
]

FILES = {
    "app/main.py": '''from fastapi import FastAPI
from app.config import settings
from app.database import engine
from app.routers import auth, users, agents, device, params, update, admin

app = FastAPI(title="HiveGreatSage Verify", version="0.1.0")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(device.router, prefix="/api/device", tags=["device"])
app.include_router(params.router, prefix="/api/params", tags=["params"])
app.include_router(update.router, prefix="/api/update", tags=["update"])
app.include_router(admin.router, prefix="/admin/api", tags=["admin"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
''',

    "app/config.py": '''from pydantic_settings import BaseSettings
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
''',

    "app/database.py": '''from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
''',

    "app/core/security.py": '''from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
import bcrypt
from app.config import settings

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
''',

    "app/core/redis_client.py": '''import redis.asyncio as redis
from app.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def get_redis():
    return redis_client
''',

    "app/routers/auth.py": '''from fastapi import APIRouter

router = APIRouter()

@router.post("/login")
async def login():
    return {"message": "login endpoint"}
''',

    "app/routers/users.py": '''from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_users():
    return {"users": []}
''',

    "app/routers/agents.py": '''from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_agents():
    return {"agents": []}
''',

    "app/routers/device.py": '''from fastapi import APIRouter

router = APIRouter()

@router.post("/heartbeat")
async def heartbeat():
    return {"status": "received"}
''',

    "app/routers/params.py": '''from fastapi import APIRouter

router = APIRouter()

@router.get("/get")
async def get_params():
    return {"params": {}}
''',

    "app/routers/update.py": '''from fastapi import APIRouter

router = APIRouter()

@router.get("/check")
async def check_update():
    return {"need_update": False}
''',

    "app/routers/admin.py": '''from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def admin_dashboard():
    return {"stats": {}}
''',

    ".env.example": '''# 应用配置
ENVIRONMENT=development
SECRET_KEY=change-this-to-a-random-secret-key-min-32-bytes

# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/hive_platform

# Redis
REDIS_URL=redis://localhost:6379/0

# 文件存储 (local 或 s3)
STORAGE_MODE=local
STORAGE_LOCAL_ROOT=/var/www/hive-updates
# S3 配置（当 STORAGE_MODE=s3 时必填）
# S3_ENDPOINT=
# S3_BUCKET=
# S3_ACCESS_KEY=
# S3_SECRET_KEY=
''',

    "requirements.txt": '''fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
asyncpg==0.29.0
alembic==1.13.0
redis==5.0.0
celery==5.4.0
python-dotenv==1.0.0
pydantic-settings==2.4.0
bcrypt==4.1.0
python-jose[cryptography]==3.3.0
loguru==0.7.2
sentry-sdk==2.8.0
''',

    "README.md": '''# HiveGreatSage-Verify

蜂巢·大圣平台 - 网络验证系统（中枢）

## 快速开始

1. 创建虚拟环境：`python -m venv venv`
2. 激活环境并安装依赖：`pip install -r requirements.txt`
3. 复制 `.env.example` 为 `.env` 并填入真实配置
4. 初始化数据库：`alembic upgrade head`
5. 启动服务：`uvicorn app.main:app --reload`

访问 http://127.0.0.1:8000/docs 查看 API 文档。
''',

    "alembic.ini": '''[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = driver://user:pass@localhost/dbname

[post_write_hooks]
hooks = black
black.type = console_scripts
black.entrypoint = black
black.options = -l 88

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
''',

    "migrations/env.py": '''import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.database import Base
from app.models.main import *
from app.models.game import *
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
''',

    "deploy/nginx.conf": '''server {
    listen 80;
    server_name your-domain.com;

    location /updates/ {
        alias /var/www/hive-updates/;
        expires 1h;
        add_header Cache-Control "public";
    }

    location /api/ {
        proxy_pass http://unix:/var/run/hive-verify.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /admin/ {
        root /var/www/hive-admin/dist;
        try_files $uri /admin/index.html;
    }
}
''',

    "deploy/systemd/hive-verify.service": '''[Unit]
Description=HiveGreatSage Verify Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/HiveGreatSage-Verify
Environment="PATH=/opt/HiveGreatSage-Verify/venv/bin"
ExecStart=/opt/HiveGreatSage-Verify/venv/bin/uvicorn app.main:app --uds /var/run/hive-verify.sock

[Install]
WantedBy=multi-user.target
''',
}


def create_directories():
    for dir_path in DIRECTORIES:
        full_path = BASE_DIR / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ 创建目录: {dir_path}")


def create_init_files():
    for pkg in PY_PACKAGES:
        init_file = BASE_DIR / pkg / "__init__.py"
        init_file.touch(exist_ok=True)
        print(f"📄 创建 __init__.py: {pkg}")


def create_files():
    for file_path, content in FILES.items():
        full_path = BASE_DIR / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_path.exists():
            full_path.write_text(content, encoding="utf-8")
            print(f"📝 创建文件: {file_path}")
        else:
            print(f"⚠️  文件已存在，跳过: {file_path}")


def main():
    print("🚀 开始生成 HiveGreatSage-Verify 项目骨架...\n")
    create_directories()
    create_init_files()
    create_files()
    print("\n✨ 骨架生成完毕！接下来：")
    print("1. 创建虚拟环境：python -m venv venv")
    print("2. 激活环境并安装依赖：pip install -r requirements.txt")
    print("3. 复制 .env.example 为 .env 并填入真实配置")
    print("4. 初始化数据库：alembic upgrade head")
    print("5. 启动服务：uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()