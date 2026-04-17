r"""
文件位置: scripts/init_data.py
文件名称: init_data.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-18
版本: v1.0.0
功能说明:
    数据库初始化脚本，创建：
      1. 第一个管理员账号
      2. 第一个游戏项目（含独立数据库自动创建）
      3. 一个测试用户（tester 级别）
      4. 为测试用户绑定游戏授权
    运行方式：python scripts/init_data.py
    幂等性：重复运行不会报错（已存在则跳过）
改进历史: 无
调试信息:
    运行前确认 .env 配置正确，PostgreSQL 和 Redis 服务正在运行。
    游戏项目库（hive_game_001）需要单独建表，脚本会自动处理。
"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.core.security import hash_password
from app.database import Base, _main_engine, _main_session_factory
from app.models.main.models import (
    Admin,
    Authorization,
    DeviceBinding,
    GameProject,
    User,
)

# ── 初始数据配置（按需修改）──────────────────────────────────
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@2026!"          # 生产环境必须修改

GAME_CODE_NAME = "game_001"
GAME_DISPLAY_NAME = "测试游戏 001"
GAME_DB_NAME = "hive_game_001"

TEST_USER_USERNAME = "test_user_001"
TEST_USER_PASSWORD = "Test@2026!"       # 生产环境必须修改


async def create_game_database() -> None:
    """
    创建游戏项目独立数据库（hive_game_001）。
    PostgreSQL 创建数据库必须在事务外执行，需要用 autocommit 连接。
    """
    # 用主库连接字符串，替换数据库名为 postgres（默认库）
    admin_url = settings.DATABASE_MAIN_URL.replace(
        "/hive_platform", "/postgres"
    )
    engine = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",   # CREATE DATABASE 不能在事务中执行
    )
    async with engine.connect() as conn:
        # 检查数据库是否已存在
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": GAME_DB_NAME},
        )
        exists = result.scalar()

        if exists:
            print(f"  ⚠️  数据库 {GAME_DB_NAME} 已存在，跳过创建")
        else:
            await conn.execute(
                text(f'CREATE DATABASE {GAME_DB_NAME} OWNER hive_user')
            )
            print(f"  ✅ 数据库 {GAME_DB_NAME} 创建成功")

    await engine.dispose()


async def create_game_tables() -> None:
    """
    在游戏数据库中建表（导入游戏库模型）。
    """
    # 导入游戏库模型，确保 Base.metadata 中包含这些表
    from app.models.game import models as game_models  # noqa: F401

    game_url = f"{settings.DATABASE_GAME_PREFIX}{GAME_CODE_NAME}"
    engine = create_async_engine(game_url, echo=False)

    async with engine.begin() as conn:
        # 只创建游戏库相关的表（通过 bind_key 过滤，这里简化为全部创建）
        await conn.run_sync(game_models.GameBase.metadata.create_all)

    await engine.dispose()
    print(f"  ✅ 游戏库 {GAME_DB_NAME} 建表完成")


async def init_main_data() -> None:
    """在主库中创建管理员、游戏项目、测试用户、授权。"""

    async with _main_session_factory() as session:

        # ── 1. 创建管理员 ────────────────────────────────────
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :u"),
            {"u": ADMIN_USERNAME},
        )
        admin_id = result.scalar()

        if admin_id:
            print(f"  ⚠️  管理员 '{ADMIN_USERNAME}' 已存在（id={admin_id}），跳过")
        else:
            admin = Admin(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                status="active",
            )
            session.add(admin)
            await session.flush()   # 获取 admin.id
            admin_id = admin.id
            print(f"  ✅ 管理员创建成功")
            print(f"     用户名：{ADMIN_USERNAME}")
            print(f"     密　码：{ADMIN_PASSWORD}")
            print(f"     ID    ：{admin_id}")

        # ── 2. 创建游戏项目 ──────────────────────────────────
        result = await session.execute(
            text("SELECT id, project_uuid FROM game_project WHERE code_name = :c"),
            {"c": GAME_CODE_NAME},
        )
        row = result.fetchone()

        if row:
            game_id, project_uuid = row
            print(f"  ⚠️  游戏项目 '{GAME_CODE_NAME}' 已存在，跳过")
            print(f"     project_uuid：{project_uuid}  ← 客户端登录时使用")
        else:
            game = GameProject(
                code_name=GAME_CODE_NAME,
                display_name=GAME_DISPLAY_NAME,
                db_name=GAME_DB_NAME,
                is_active=True,
            )
            session.add(game)
            await session.flush()
            game_id = game.id
            print(f"  ✅ 游戏项目创建成功")
            print(f"     code_name    ：{GAME_CODE_NAME}")
            print(f"     project_uuid ：{game.project_uuid}  ← 客户端登录时使用")
            print(f"     ID           ：{game_id}")

        # ── 3. 创建测试用户 ──────────────────────────────────
        result = await session.execute(
            text('SELECT id FROM "user" WHERE username = :u'),
            {"u": TEST_USER_USERNAME},
        )
        user_id = result.scalar()

        if user_id:
            print(f"  ⚠️  测试用户 '{TEST_USER_USERNAME}' 已存在（id={user_id}），跳过")
        else:
            user = User(
                username=TEST_USER_USERNAME,
                password_hash=hash_password(TEST_USER_PASSWORD),
                user_level="tester",
                created_by_admin=True,      # tester 必须由管理员创建
                status="active",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            print(f"  ✅ 测试用户创建成功")
            print(f"     用户名：{TEST_USER_USERNAME}")
            print(f"     密　码：{TEST_USER_PASSWORD}")
            print(f"     级　别：tester（无设备绑定上限）")
            print(f"     ID    ：{user_id}")

        # ── 4. 创建授权记录 ──────────────────────────────────
        result = await session.execute(
            text(
                'SELECT id FROM "authorization" '
                "WHERE user_id = :u AND game_project_id = :g"
            ),
            {"u": user_id, "g": game_id},
        )
        auth_exists = result.scalar()

        if auth_exists:
            print(f"  ⚠️  授权记录已存在，跳过")
        else:
            auth = Authorization(
                user_id=user_id,
                game_project_id=game_id,
                status="active",
                valid_until=None,           # 永久有效
            )
            session.add(auth)
            print(f"  ✅ 授权记录创建成功（用户 {user_id} → 游戏 {game_id}，永久有效）")

        await session.commit()


async def main() -> None:
    print("=" * 55)
    print(" HiveGreatSage-Verify 数据库初始化")
    print("=" * 55)

    print("\n[1/3] 创建游戏项目数据库...")
    await create_game_database()

    print("\n[2/3] 游戏库建表...")
    try:
        await create_game_tables()
    except Exception as e:
        print(f"  ⚠️  游戏库建表跳过（{e}）")
        print(f"      如游戏库模型尚未实现，属正常情况，不影响主库初始化")

    print("\n[3/3] 初始化主库数据...")
    await init_main_data()

    print("\n" + "=" * 55)
    print(" ✅ 初始化完成！")
    print("=" * 55)
    print("\n现在可以用以下信息测试登录接口：")
    print(f"  POST http://localhost:8000/api/auth/login")
    print(f"  username          : {TEST_USER_USERNAME}")
    print(f"  password          : {TEST_USER_PASSWORD}")
    print(f"  project_uuid      : （见上方输出的 project_uuid）")
    print(f"  device_fingerprint: test_device_001")
    print(f"  client_type       : android")
    print()

    # 关闭主库连接池
    await _main_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())