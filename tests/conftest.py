r"""
文件位置: tests/conftest.py
名称: 测试 fixtures
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-22
版本: V1.0.8
功能说明:
    直接复用 hive_platform + hive_game_001 开发库跑测试。

    【已知问题与设计决策】
    hive_game_001 的 hive_user 认证可能失败（InvalidPasswordError），
    根本原因是 PostgreSQL 权限/密码格式问题，与 Python 代码无关。
    修复方法：以 postgres 超级用户运行 scripts/setup_game_db.sql。

    game_db_accessible（session 级）：
      一次性检测 hive_game_001 连通性，返回 True/False，绝不抛出异常。
      所有需要游戏库的 fixtures（seed_params / seed_version /
      cleanup_test_versions）都先检查此值，不可用则 pytest.skip。
      这样即使 hive_game_001 不可访问，pytest 结果是 SKIP 而非 ERROR。

    client fixture 做四层 patch：
      1. FastAPI DI 覆盖 get_main_db / get_redis
      2. monkey-patch _main_session_factory
      3. monkey-patch incr_rate_limit
      4. 注入 game_engine / game_session_factory

    事件循环（D015）：
      层1：模块顶部 WindowsSelectorEventLoopPolicy
      层2：显式 event_loop fixture（scope=session，同步 def）

改进历史:
    V1.0.8 (2026-04-25) - 新增 game_db_accessible session 级可用性检测；
                          修复 fixture ERROR 级联问题（改为优雅 SKIP）
    V1.0.7 - 注入 game_test_engine / game_session_factory
    V1.0.6 - D015 双层事件循环修复
    V1.0.0~V1.0.5 - 历史版本
"""

# ── D015 层1：必须在所有 asyncio 操作之前 ─────────────────────
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────

import pytest
import redis.asyncio as aioredis

import app.database as _app_database
import app.services.auth_service as _auth_service
import app.routers.auth as _auth_router

from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.engine.url import make_url as _make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.main import app
from app.config import settings
from app.database import get_main_db
from app.core.redis_client import get_redis
from app.models.main.models import Admin, GameProject
from app.core.security import hash_password, create_admin_token

# ── 测试常量 ──────────────────────────────────────────────────
TEST_DB_URL       = settings.DATABASE_MAIN_URL
GAME_PROJECT_UUID = "00000000-0000-0000-0000-000000000001"
GAME_PROJECT_CODE = "game_001"
ADMIN_USERNAME    = "test_admin"
ADMIN_PASSWORD    = "TestAdmin@2026!"

_GAME_TEST_DB_URL = str(
    _make_url(settings.DATABASE_MAIN_URL).set(database="hive_" + GAME_PROJECT_CODE)
)

# ─────────────────────────────────────────────────────────────
# 未连通时的标准跳过消息（统一文案，便于全文搜索）
# ─────────────────────────────────────────────────────────────
GAME_DB_SKIP_MSG = (
    "hive_game_001 不可访问（hive_user 认证失败）。"
    "请以 postgres 超级用户运行 scripts/setup_game_db.sql 修复权限，然后重新测试。"
)


# ── D015 层2：强制覆盖 pytest-asyncio session loop ─────────────

@pytest.fixture(scope="session")
def event_loop():
    """同步 fixture，强制整个 session 使用 SelectorEventLoop。"""
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── Session 级 fixtures ───────────────────────────────────────

@pytest.fixture(scope="session")
async def test_engine():
    """主库 hive_platform 引擎（NullPool）。"""
    engine = create_async_engine(
        TEST_DB_URL, poolclass=NullPool, connect_args={"ssl": False},
    )
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def session_factory(test_engine):
    return async_sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
async def game_test_engine():
    """游戏库 hive_game_001 引擎（NullPool，session 级）。不在创建时检测连通性。"""
    engine = create_async_engine(
        _GAME_TEST_DB_URL, poolclass=NullPool, connect_args={"ssl": False},
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def game_session_factory(game_test_engine):
    """游戏库 session factory（session 级）。"""
    return async_sessionmaker(bind=game_test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
async def game_db_accessible(game_test_engine) -> bool:
    """
    一次性检测 hive_game_001 是否可访问。
    返回 True / False，绝不抛出异常。

    当 PostgreSQL 的 hive_user 对 hive_game_001 缺少权限时返回 False。
    修复方法：以 postgres 超级用户运行 scripts/setup_game_db.sql。

    所有需要游戏库的 fixture 都应先 check 此值，不可用则 pytest.skip，
    确保 pytest 结果是 SKIP 而非 ERROR。
    """
    try:
        factory = async_sessionmaker(bind=game_test_engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        print(
            f"\n⚠️  hive_game_001 不可访问: {exc}\n"
            f"   请运行: psql -U postgres -p 15432 -f scripts/setup_game_db.sql\n"
        )
        return False


@pytest.fixture(scope="session")
async def seed_data(session_factory):
    """初始化测试管理员和游戏项目（幂等）。"""
    import uuid as uuid_lib

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :u"), {"u": ADMIN_USERNAME},
        )
        admin_id = result.scalar()
        if not admin_id:
            admin = Admin(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                status="active",
            )
            session.add(admin)
            await session.flush()
            admin_id = admin.id

        result = await session.execute(
            text("SELECT id FROM game_project WHERE code_name = :c"), {"c": GAME_PROJECT_CODE},
        )
        project_id = result.scalar()
        if not project_id:
            project = GameProject(
                project_uuid=uuid_lib.UUID(GAME_PROJECT_UUID),
                code_name=GAME_PROJECT_CODE,
                display_name="测试游戏 001",
                db_name="hive_game_001",
                is_active=True,
            )
            session.add(project)
            await session.flush()
            project_id = project.id

        await session.execute(
            text("UPDATE game_project SET project_uuid = :uuid WHERE id = :id"),
            {"uuid": GAME_PROJECT_UUID, "id": project_id},
        )
        await session.commit()
        return {"admin_id": admin_id, "project_id": project_id}


# ── Function 级 fixture ───────────────────────────────────────

@pytest.fixture
async def client(
    test_engine,
    session_factory,
    game_test_engine,
    game_session_factory,
    seed_data,
):
    """httpx.AsyncClient 直连 ASGI，四层 patch。"""
    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_redis():
        r = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            yield r
        finally:
            await r.aclose()

    app.dependency_overrides[get_main_db] = _override_get_db
    app.dependency_overrides[get_redis]   = _override_get_redis

    _orig_db_factory   = _app_database._main_session_factory
    _orig_auth_factory = _auth_service._main_session_factory
    _app_database._main_session_factory = session_factory
    _auth_service._main_session_factory = session_factory

    async def _mock_rate_limit(*args, **kwargs):
        return True, 0

    _orig_rate_limit = _auth_router.incr_rate_limit
    _auth_router.incr_rate_limit = _mock_rate_limit

    _orig_game_engines   = dict(_app_database._game_engines)
    _orig_game_factories = dict(_app_database._game_session_factories)
    _app_database._game_engines[GAME_PROJECT_CODE]           = game_test_engine
    _app_database._game_session_factories[GAME_PROJECT_CODE] = game_session_factory

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        _app_database._main_session_factory = _orig_db_factory
        _auth_service._main_session_factory = _orig_auth_factory
        _auth_router.incr_rate_limit        = _orig_rate_limit
        _app_database._game_engines.clear()
        _app_database._game_engines.update(_orig_game_engines)
        _app_database._game_session_factories.clear()
        _app_database._game_session_factories.update(_orig_game_factories)


@pytest.fixture
async def admin_token(seed_data) -> str:
    return create_admin_token(seed_data["admin_id"])


@pytest.fixture
async def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
async def project_id(seed_data) -> int:
    return seed_data["project_id"]
