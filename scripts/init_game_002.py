r"""
文件位置: scripts/init_game_002.py
文件名称: init_game_002.py
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-27
版本: V1.0.0
功能及相关说明:
  为 game_002（椰芽）初始化数据：
    1. 创建游戏项目记录（project_uuid 固定为 07238db5-...）
    2. 创建游戏库 hive_game_game_002 并建表
    3. 创建 tester 级别测试用户 yeya_tester
    4. 为测试用户绑定 game_002 授权（永久有效）
  幂等：重复运行不报错（已存在则跳过）

改进内容:
  V1.0.0 - 初始版本

调试信息:
  运行前确认 .env 配置正确，PostgreSQL 和 Redis 正在运行。
  运行命令：python scripts/init_game_002.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core.security import hash_password
from app.database import _main_engine, _main_session_factory
from app.models.main.models import Authorization, GameProject, User

# ── 固定配置（与 PCControl local.yaml 保持一致）────────────────
GAME_CODE_NAME    = "game_002"
GAME_DISPLAY_NAME = "椰芽"
GAME_DB_NAME      = "hive_game_game_002"
GAME_PROJECT_UUID = "07238db5-129a-4408-b82a-e025be4652a1"

TEST_USER_USERNAME = "yeya_tester"
TEST_USER_PASSWORD = "Yeya@2026!"


async def create_game_database() -> None:
    base_url = make_url(settings.DATABASE_MAIN_URL).set(database="postgres")
    engine = create_async_engine(
        base_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"ssl": False},
    )
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": GAME_DB_NAME},
        )
        if result.scalar():
            print(f"  ⚠️  数据库 {GAME_DB_NAME} 已存在，跳过")
        else:
            await conn.execute(text(f"CREATE DATABASE {GAME_DB_NAME} OWNER hive_user"))
            print(f"  ✅ 数据库 {GAME_DB_NAME} 创建成功")
    await engine.dispose()


async def create_game_tables() -> None:
    try:
        from app.models.game import models as game_models  # noqa: F401
        game_url = make_url(settings.DATABASE_MAIN_URL).set(database=GAME_DB_NAME)
        engine = create_async_engine(game_url, echo=False, connect_args={"ssl": False})
        async with engine.begin() as conn:
            await conn.run_sync(game_models.GameBase.metadata.create_all)
        await engine.dispose()
        print(f"  ✅ 游戏库 {GAME_DB_NAME} 建表完成")
    except Exception as e:
        print(f"  ⚠️  游戏库建表跳过（{e}）")


async def init_main_data() -> None:
    async with _main_session_factory() as session:

        # ── 1. 游戏项目 ─────────────────────────────────────
        result = await session.execute(
            text("SELECT id FROM game_project WHERE code_name = :c"),
            {"c": GAME_CODE_NAME},
        )
        row = result.fetchone()

        if row:
            game_id = row[0]
            print(f"  ⚠️  游戏项目 '{GAME_CODE_NAME}' 已存在（id={game_id}），跳过")
        else:
            game = GameProject(
                project_uuid=GAME_PROJECT_UUID,
                code_name=GAME_CODE_NAME,
                display_name=GAME_DISPLAY_NAME,
                db_name=GAME_DB_NAME,
                is_active=True,
            )
            session.add(game)
            await session.flush()
            game_id = game.id
            print(f"  ✅ 游戏项目创建成功")
            print(f"     project_uuid : {GAME_PROJECT_UUID}")
            print(f"     code_name    : {GAME_CODE_NAME}")
            print(f"     db_name      : {GAME_DB_NAME}")
            print(f"     ID           : {game_id}")

        # ── 2. 测试用户 ─────────────────────────────────────
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
                created_by_admin=True,
                status="active",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            print(f"  ✅ 测试用户创建成功")
            print(f"     用户名 : {TEST_USER_USERNAME}")
            print(f"     密　码 : {TEST_USER_PASSWORD}")
            print(f"     级　别 : tester（无设备绑定上限）")
            print(f"     ID     : {user_id}")

        # ── 3. 授权记录 ─────────────────────────────────────
        result = await session.execute(
            text(
                'SELECT id FROM "authorization" '
                "WHERE user_id = :u AND game_project_id = :g"
            ),
            {"u": user_id, "g": game_id},
        )
        if result.scalar():
            print(f"  ⚠️  授权记录已存在，跳过")
        else:
            auth = Authorization(
                user_id=user_id,
                game_project_id=game_id,
                status="active",
                valid_until=None,
            )
            session.add(auth)
            print(f"  ✅ 授权创建成功（yeya_tester → game_002，永久有效）")

        await session.commit()


async def main() -> None:
    print("=" * 55)
    print(" game_002（椰芽）初始化")
    print("=" * 55)

    print("\n[1/3] 创建游戏数据库...")
    await create_game_database()

    print("\n[2/3] 游戏库建表...")
    await create_game_tables()

    print("\n[3/3] 初始化主库数据...")
    await init_main_data()

    print("\n" + "=" * 55)
    print(" ✅ 初始化完成！")
    print("=" * 55)
    print("\nPCControl 登录信息：")
    print(f"  用户名           : {TEST_USER_USERNAME}")
    print(f"  密码             : {TEST_USER_PASSWORD}")
    print(f"  project_uuid     : {GAME_PROJECT_UUID}")
    print()

    await _main_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
