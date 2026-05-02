r"""
文件位置: scripts/init_game_002.py
文件名称: init_game_002.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    开发期 game_002（椰芽）初始化脚本。

    当前脚本只用于开发 / 真机联调环境：
      1. 创建 game_002 游戏项目记录。
      2. 创建与运行时 get_game_db(code_name) 一致的游戏库 hive_game_002。
      3. 创建开发测试用户 yeya_tester。
      4. 为测试用户写入 game_002 项目授权。

    重要边界:
      1. 本脚本不是生产初始化脚本。
      2. 本脚本不替代管理后台创建项目流程。
      3. 本脚本不替代 Alembic 迁移。
      4. 本脚本不打印测试用户密码。
      5. 测试用户密码必须通过环境变量或交互式输入提供。

    数据库命名修正:
      旧脚本使用 hive_game_game_002。
      当前运行时代码 get_game_db("game_002") 会推导 hive_game_002。
      因此本脚本统一使用 hive_game_002，避免脚本建库与运行时查库不一致。

可选环境变量:
    HGS_GAME_002_USERNAME
    HGS_GAME_002_PASSWORD

示例:
    HGS_GAME_002_USERNAME=yeya_tester HGS_GAME_002_PASSWORD='your-strong-password' python scripts/init_game_002.py

改进历史:
    V1.1.0 (2026-05-02) - 移除测试用户明文密码；修正游戏库命名；显式写入授权等级和设备数。
    V1.0.0 (2026-04-27) - 初始版本。

调试信息:
    运行前确认 .env 配置正确，PostgreSQL 和 Redis 正在运行。
    运行命令：python scripts/init_game_002.py
"""

import asyncio
import getpass
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core.security import hash_password
from app.database import _main_engine, _main_session_factory
from app.models.main.models import Authorization, GameProject, User


GAME_CODE_NAME = "game_002"
GAME_DISPLAY_NAME = "椰芽"
GAME_DB_NAME = "hive_game_002"
GAME_PROJECT_UUID = "07238db5-129a-4408-b82a-e025be4652a1"

DEFAULT_TEST_USER_USERNAME = "yeya_tester"
MIN_TEST_USER_PASSWORD_LENGTH = 12

DB_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_db_identifier(value: str) -> None:
    if not DB_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"非法数据库标识符：{value}")


def _read_test_username() -> str:
    username = os.getenv("HGS_GAME_002_USERNAME", "").strip()
    if username:
        return username
    return DEFAULT_TEST_USER_USERNAME


def _validate_test_password(password: str) -> None:
    if not password:
        raise ValueError("测试用户密码不能为空。")

    if len(password) < MIN_TEST_USER_PASSWORD_LENGTH:
        raise ValueError(
            f"测试用户密码长度不能少于 {MIN_TEST_USER_PASSWORD_LENGTH} 位。"
        )


def _read_test_password() -> str:
    env_password = os.getenv("HGS_GAME_002_PASSWORD", "")
    if env_password:
        _validate_test_password(env_password)
        return env_password

    if not sys.stdin.isatty():
        raise RuntimeError(
            "未提供测试用户密码。请设置环境变量 HGS_GAME_002_PASSWORD 后再运行。"
        )

    password = getpass.getpass("请输入 game_002 测试用户密码（不会回显）：")
    confirm_password = getpass.getpass("请再次输入 game_002 测试用户密码：")

    if password != confirm_password:
        raise ValueError("两次输入的测试用户密码不一致。")

    _validate_test_password(password)
    return password


async def create_game_database() -> None:
    _validate_db_identifier(GAME_DB_NAME)

    base_url = make_url(settings.DATABASE_MAIN_URL).set(database="postgres")
    engine = create_async_engine(
        base_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"ssl": False},
    )

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": GAME_DB_NAME},
            )
            if result.scalar():
                print(f"  INFO 数据库 {GAME_DB_NAME} 已存在，跳过。")
            else:
                await conn.execute(
                    text(f'CREATE DATABASE "{GAME_DB_NAME}" OWNER hive_user')
                )
                print(f"  OK 数据库 {GAME_DB_NAME} 创建成功。")
    finally:
        await engine.dispose()


async def create_game_tables() -> None:
    try:
        from app.models.game import models as game_models

        game_url = make_url(settings.DATABASE_MAIN_URL).set(database=GAME_DB_NAME)
        engine = create_async_engine(game_url, echo=False, connect_args={"ssl": False})

        try:
            async with engine.begin() as conn:
                await conn.run_sync(game_models.GameBase.metadata.create_all)
        finally:
            await engine.dispose()

        print(f"  OK 游戏库 {GAME_DB_NAME} 建表完成。")
    except Exception as exc:
        print(f"  WARN 游戏库建表失败或跳过：{exc}")
        raise


async def _ensure_game_project(session) -> int:
    result = await session.execute(
        text("SELECT id, db_name FROM game_project WHERE code_name = :code_name"),
        {"code_name": GAME_CODE_NAME},
    )
    row = result.fetchone()

    if row:
        game_id = row[0]
        current_db_name = row[1]

        if current_db_name != GAME_DB_NAME:
            await session.execute(
                text(
                    "UPDATE game_project "
                    "SET db_name = :db_name, project_type = 'game', is_active = TRUE "
                    "WHERE id = :id"
                ),
                {"db_name": GAME_DB_NAME, "id": game_id},
            )
            print(
                "  WARN 游戏项目已存在，但 db_name 与运行时命名不一致，已修正。"
            )
            print(f"       旧 db_name：{current_db_name}")
            print(f"       新 db_name：{GAME_DB_NAME}")
            print("       如旧物理库存在，请人工确认后再决定是否删除。")
        else:
            print(f"  INFO 游戏项目 '{GAME_CODE_NAME}' 已存在（id={game_id}），跳过。")

        return game_id

    game = GameProject(
        project_uuid=GAME_PROJECT_UUID,
        code_name=GAME_CODE_NAME,
        display_name=GAME_DISPLAY_NAME,
        project_type="game",
        db_name=GAME_DB_NAME,
        is_active=True,
    )
    session.add(game)
    await session.flush()

    print("  OK 游戏项目创建成功。")
    print(f"     project_uuid : {GAME_PROJECT_UUID}")
    print(f"     code_name    : {GAME_CODE_NAME}")
    print(f"     db_name      : {GAME_DB_NAME}")
    print(f"     ID           : {game.id}")

    return game.id


async def _ensure_test_user(session) -> int:
    username = _read_test_username()

    result = await session.execute(
        text('SELECT id FROM "user" WHERE username = :username'),
        {"username": username},
    )
    user_id = result.scalar()

    if user_id:
        print(f"  INFO 测试用户 '{username}' 已存在（id={user_id}），跳过创建。")
        return user_id

    password = _read_test_password()

    user = User(
        username=username,
        password_hash=hash_password(password),
        created_by_admin=True,
        status="active",
    )
    # 注意：User 模型已删除 user_level / max_devices 字段。
    # 项目授权等级和设备数统一通过 Authorization 管理。
    session.add(user)
    await session.flush()

    print("  OK 测试用户创建成功。")
    print(f"     用户名 : {username}")
    print("     密码   : 已设置，出于安全原因不显示。")
    print("     授权   : 后续写入 Authorization.user_level=tester / authorized_devices=0")
    print(f"     ID     : {user.id}")

    return user.id


async def _ensure_authorization(session, user_id: int, game_id: int) -> None:
    result = await session.execute(
        text(
            'SELECT id, user_level, authorized_devices, status '
            'FROM "authorization" '
            "WHERE user_id = :user_id AND game_project_id = :game_project_id"
        ),
        {"user_id": user_id, "game_project_id": game_id},
    )
    row = result.fetchone()

    if row:
        authorization_id = row[0]
        current_level = row[1]
        current_devices = row[2]
        current_status = row[3]

        if (
            current_level != "tester"
            or current_devices != 0
            or current_status != "active"
        ):
            await session.execute(
                text(
                    'UPDATE "authorization" '
                    "SET user_level = 'tester', "
                    "    authorized_devices = 0, "
                    "    status = 'active', "
                    "    valid_until = NULL "
                    "WHERE id = :id"
                ),
                {"id": authorization_id},
            )
            print(
                "  WARN 授权记录已存在，但授权字段不是目标值，已修正为 tester / 0 / active。"
            )
        else:
            print("  INFO 授权记录已存在，且字段正确，跳过。")

        return

    auth = Authorization(
        user_id=user_id,
        game_project_id=game_id,
        user_level="tester",
        authorized_devices=0,
        status="active",
        valid_until=None,
    )
    session.add(auth)
    print("  OK 授权创建成功（tester / 0 设备上限 / 永久有效）。")


async def init_main_data() -> None:
    async with _main_session_factory() as session:
        game_id = await _ensure_game_project(session)
        user_id = await _ensure_test_user(session)
        await _ensure_authorization(session, user_id=user_id, game_id=game_id)
        await session.commit()


async def main() -> None:
    print("=" * 55)
    print(" game_002（椰芽）开发数据初始化")
    print("=" * 55)
    print()
    print("WARN 本脚本仅限开发 / 真机联调环境使用。")
    print("WARN 不得把本脚本作为生产初始化流程。")
    print()

    print("[1/3] 创建游戏数据库...")
    await create_game_database()

    print()
    print("[2/3] 游戏库建表...")
    await create_game_tables()

    print()
    print("[3/3] 初始化主库数据...")
    await init_main_data()

    print()
    print("=" * 55)
    print(" OK 初始化完成")
    print("=" * 55)
    print()
    print("PCControl 联调信息：")
    print(f"  用户名       : {_read_test_username()}")
    print("  密码         : 已设置，出于安全原因不显示。")
    print(f"  project_uuid : {GAME_PROJECT_UUID}")
    print(f"  code_name    : {GAME_CODE_NAME}")
    print(f"  db_name      : {GAME_DB_NAME}")
    print()

    await _main_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())