r"""
文件位置: scripts/provision_game_db.py
名称: 游戏库初始化脚本
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-06
版本: V1.0.0
功能及相关说明:
  只负责创建或修复指定游戏项目数据库，并执行游戏库表结构初始化。
  不清理主库、不删除游戏库、不清空 Redis、不替代 reset_to_clean.py。

改进内容:
  V1.0.0 - 替代被删除的误命名 scripts/setup_game_db.py。

调试信息:
  已知问题: 需要调用账号具备 CREATE DATABASE / GRANT 权限。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.models.game.models import GameBase

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def _safe_identifier(value: str, label: str) -> str:
    if not _SAFE_IDENTIFIER.match(value):
        raise ValueError(f"{label} 只能使用小写字母、数字、下划线，且必须以小写字母开头: {value!r}")
    return value


def _db_name_from_code(code: str) -> str:
    code = _safe_identifier(code, "code")
    return f"hive_{code}"


def _quote_ident(value: str) -> str:
    # 标识符已通过白名单校验，这里只做 SQL 标识符包裹。
    return f'"{value}"'


async def _database_exists(admin_url: str, db_name: str) -> bool:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                {"db_name": db_name},
            )
            return result.scalar_one_or_none() is not None
    finally:
        await engine.dispose()


async def _create_database(admin_url: str, db_name: str, owner: str | None) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            owner_sql = f" OWNER {_quote_ident(owner)}" if owner else ""
            await conn.execute(text(f"CREATE DATABASE {_quote_ident(db_name)}{owner_sql}"))
    finally:
        await engine.dispose()


async def _grant_permissions(admin_url: str, db_name: str, db_user: str | None) -> None:
    if not db_user:
        return
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"GRANT CONNECT ON DATABASE {_quote_ident(db_name)} TO {_quote_ident(db_user)}"))
    finally:
        await engine.dispose()


async def _create_game_tables(game_db_url: str) -> None:
    engine = create_async_engine(game_db_url, connect_args={"ssl": False})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(GameBase.metadata.create_all)
            await _sync_device_runtime_schema(conn)
    finally:
        await engine.dispose()


async def _sync_device_runtime_schema(conn) -> None:
    """
    确保已存在游戏库的 device_runtime 结构与当前模型一致。

    背景：GameBase.metadata.create_all() 不会修改已存在表。当前统一为
    device_id 作为设备运行态主键。
    """
    table_exists = await conn.scalar(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'device_runtime'
        )
    """))
    if not table_exists:
        return

    rows = await conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'device_runtime'
    """))
    columns = {row[0] for row in rows}

    if "device_id" not in columns:
        await conn.execute(text("ALTER TABLE device_runtime ADD COLUMN device_id VARCHAR(64)"))
        columns.add("device_id")

    if "connection_type" not in columns:
        await conn.execute(text("ALTER TABLE device_runtime ADD COLUMN connection_type VARCHAR(16)"))

    if "connection_label" not in columns:
        await conn.execute(text("ALTER TABLE device_runtime ADD COLUMN connection_label VARCHAR(255)"))

    await conn.execute(text("ALTER TABLE device_runtime DROP CONSTRAINT IF EXISTS device_runtime_pkey"))
    await conn.execute(text("ALTER TABLE device_runtime ALTER COLUMN device_id TYPE VARCHAR(64)"))
    await conn.execute(text("ALTER TABLE device_runtime ALTER COLUMN device_id SET NOT NULL"))
    await conn.execute(text("ALTER TABLE device_runtime ADD CONSTRAINT device_runtime_pkey PRIMARY KEY (device_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_runtime_user ON device_runtime (user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_runtime_last_seen ON device_runtime (last_seen)"))


async def provision_game_db(code: str, db_name: str | None = None) -> None:
    db_name = _safe_identifier(db_name, "db_name") if db_name else _db_name_from_code(code)

    main_url = make_url(settings.DATABASE_MAIN_URL)
    db_user = main_url.username

    admin_url = os.getenv("DATABASE_ADMIN_URL")
    if not admin_url:
        # NOTE: str(URL) hides password as "***"; must render real DSN.
        admin_url = main_url.set(database="postgres").render_as_string(hide_password=False)

    game_db_url = main_url.set(database=db_name).render_as_string(hide_password=False)

    if await _database_exists(admin_url, db_name):
        print(f"[OK] database exists: {db_name}")
    else:
        await _create_database(admin_url, db_name, owner=db_user)
        print(f"[OK] database created: {db_name}")

    await _grant_permissions(admin_url, db_name, db_user)
    await _create_game_tables(game_db_url)
    print(f"[OK] game tables ready: {db_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="创建或修复 HiveGreatSage 游戏库")
    parser.add_argument("--code", required=True, help="游戏项目 code_name，例如 game_001")
    parser.add_argument("--db-name", default=None, help="可选，显式指定数据库名，例如 hive_game_001")
    args = parser.parse_args()

    asyncio.run(provision_game_db(code=args.code, db_name=args.db_name))


if __name__ == "__main__":
    main()
