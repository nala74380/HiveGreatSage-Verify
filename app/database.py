r"""
文件位置: app/database.py
文件名称: database.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.1
功能说明:
    数据库连接管理。支持：
      1. 主库 hive_platform（用户管理，固定连接）
      2. 游戏库 hive_game_{code_name}（按游戏项目动态创建连接）
    提供 FastAPI 依赖注入用的 get_main_db() 和 get_game_db(code_name) 函数。
    所有引擎使用 SQLAlchemy 2.0 async 模式 + asyncpg 驱动。
改进历史: 无
调试信息:
    连接失败时检查 .env 中的 DATABASE_MAIN_URL 和 PostgreSQL 服务是否启动。
    WSL2 环境下 PostgreSQL 监听地址确认为 127.0.0.1 而非 localhost（IPv6 问题）。
    Windows 开发环境：asyncpg 默认尝试 SSL 握手，开发库未启用 SSL 时会抛出
    ConnectionRefusedError [WinError 1225]，通过 connect_args={"ssl": False} 禁用。
改进历史:
    v1.0.1 - 主库引擎和游戏库引擎均加入 connect_args={"ssl": False}，
             修复 Windows 开发环境 asyncpg SSL 握手失败问题（WinError 1225）
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.engine.url import make_url as _make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── ORM 基类（所有 Model 继承此类）───────────────────────────
class Base(DeclarativeBase):
    pass


# ── 主库引擎（hive_platform，全局单例）───────────────────────
_main_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_MAIN_URL,
    echo=settings.DEBUG,            # DEBUG 模式下打印所有 SQL
    pool_size=10,                   # 连接池大小
    max_overflow=20,                # 超出 pool_size 后最多额外创建的连接数
    pool_pre_ping=True,             # 每次取连接前 ping 一次，自动处理断线重连
    connect_args={"ssl": False},    # 禁用 SSL：开发环境未启用 SSL，asyncpg 默认会尝试握手导致 WinError 1225
)

_main_session_factory = async_sessionmaker(
    bind=_main_engine,
    expire_on_commit=False,         # commit 后对象属性不失效，减少额外查询
    class_=AsyncSession,
)


async def get_main_db() -> AsyncGenerator[AsyncSession, Any]:
    """
    FastAPI 依赖注入：获取主库（hive_platform）的数据库会话。

    用法：
        @router.get("/")
        async def some_endpoint(db: AsyncSession = Depends(get_main_db)):
            ...
    """
    async with _main_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── 游戏库引擎池（按游戏 code_name 动态创建，缓存复用）─────────
_game_engines: dict[str, AsyncEngine] = {}
_game_session_factories: dict[str, async_sessionmaker] = {}


def _get_game_engine(code_name: str) -> AsyncEngine:
    """
    获取或创建指定游戏库的引擎（懒加载，首次调用时创建并缓存）。
    code_name 示例：'game_001'，对应数据库 hive_game_001。
    """
    if code_name not in _game_engines:
        # D003 修复：DATABASE_GAME_PREFIX 已含 "hive_game_" 后缀，
        # 若直接拼接 code_name="game_001" 会变成 hive_game_game_001。
        # 改用 make_url 基于主库连接串只替换数据库名：
        # "hive_" + "game_001" = "hive_game_001"，与 game_project.db_name 一致。
        db_name = "hive_" + code_name
        url = str(_make_url(settings.DATABASE_MAIN_URL).set(database=db_name))
        _game_engines[code_name] = create_async_engine(
            url,
            echo=settings.DEBUG,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={"ssl": False},    # 同主库，禁用 SSL
        )
        _game_session_factories[code_name] = async_sessionmaker(
            bind=_game_engines[code_name],
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _game_engines[code_name]


def get_game_db(code_name: str):
    """
    FastAPI 依赖注入工厂：获取指定游戏库的数据库会话。

    用法（在路由函数中）：
        @router.get("/device/list")
        async def list_devices(
            game_db: AsyncSession = Depends(get_game_db("game_001"))
        ):
            ...

    或者动态传入（从路径参数获取 code_name）：
        async def some_endpoint(code_name: str, ...):
            async with _game_session_factories[code_name]() as session:
                ...
    """
    _get_game_engine(code_name)             # 确保引擎已创建

    async def _get_session() -> AsyncGenerator[AsyncSession, Any]:
        async with _game_session_factories[code_name]() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _get_session


async def dispose_all_engines() -> None:
    """
    关闭所有数据库连接池（应用关闭时调用）。
    在 main.py 的 lifespan 事件中注册。
    """
    await _main_engine.dispose()
    for engine in _game_engines.values():
        await engine.dispose()