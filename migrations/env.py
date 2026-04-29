import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.database import Base
from app.models.main.models import (  # noqa: F401 — 导入确保 ORM 模型注册到 Base.metadata
    Admin,
    Agent,
    Authorization,
    DeviceBinding,
    GameProject,
    LoginLog,
    User,
)
# 注意：游戏库模型（GameBase）不在此导入。
# 游戏表不经过 Alembic，由 GameBase.metadata.create_all() 在游戏库初始化时建表。
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 只迁移主库（hive_platform）的表，不包含游戏库表
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = settings.DATABASE_MAIN_URL
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
    configuration["sqlalchemy.url"] = settings.DATABASE_MAIN_URL
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
