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

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

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
    engine = create_async_engine(game_db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(GameBase.metadata.create_all)
    finally:
        await engine.dispose()


async def provision_game_db(code: str, db_name: str | None = None) -> None:
    db_name = _safe_identifier(db_name, "db_name") if db_name else _db_name_from_code(code)

    main_url = make_url(settings.DATABASE_MAIN_URL)
    db_user = main_url.username

    admin_url = os.getenv("DATABASE_ADMIN_URL")
    if not admin_url:
        admin_url = str(main_url.set(database="postgres"))

    game_db_url = str(main_url.set(database=db_name))

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
