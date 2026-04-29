r"""
文件位置: scripts/setup_game_db.py
名称: 游戏项目数据库创建脚本
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.0.0
功能说明:
    为指定游戏项目创建独立 PostgreSQL 数据库并建表。
    需要先通过管理后台 API 注册游戏项目，再运行本脚本建库。

    运行方式：
        python scripts/setup_game_db.py --code yeya --name "椰芽"
        python scripts/setup_game_db.py --code yeya  （name 默认与 code 相同）

    完成后在管理后台 POST /admin/api/projects/ 注册项目时，
    db_name 字段填写此处创建的数据库名（格式：hive_{code_name}）。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings
from app.models.game import models as game_models   # noqa: F401


async def create_game_database(db_name: str) -> None:
    """创建游戏项目独立数据库。"""
    base_url = make_url(settings.DATABASE_MAIN_URL).set(database="postgres")
    engine = create_async_engine(
        base_url, isolation_level="AUTOCOMMIT", connect_args={"ssl": False}
    )
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        )
        if result.scalar():
            print(f"  ℹ️  数据库 {db_name} 已存在，跳过创建")
        else:
            await conn.execute(text(f"CREATE DATABASE {db_name} OWNER hive_user"))
            print(f"  ✅ 数据库 {db_name} 创建成功")
    await engine.dispose()


async def create_game_tables(db_name: str) -> None:
    """在游戏数据库中建表。"""
    game_url = make_url(settings.DATABASE_MAIN_URL).set(database=db_name)
    engine = create_async_engine(game_url, echo=False, connect_args={"ssl": False})
    async with engine.begin() as conn:
        await conn.run_sync(game_models.GameBase.metadata.create_all)
    await engine.dispose()
    print(f"  ✅ 游戏库 {db_name} 建表完成")


async def grant_permissions(db_name: str) -> None:
    """授予 hive_user 对游戏库的完整权限。"""
    base_url = make_url(settings.DATABASE_MAIN_URL).set(database=db_name)
    engine = create_async_engine(base_url, echo=False, connect_args={"ssl": False})
    async with engine.begin() as conn:
        await conn.execute(text("GRANT USAGE ON SCHEMA public TO hive_user"))
        await conn.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hive_user"))
        await conn.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hive_user"))
    await engine.dispose()
    print(f"  ✅ {db_name} 权限授予完成")


async def main(code_name: str, display_name: str) -> None:
    # 数据库命名规则：hive_{code_name}
    db_name = f"hive_{code_name}"

    print("=" * 55)
    print(f" 创建游戏项目库：{display_name} ({code_name})")
    print(f" 数据库名：{db_name}")
    print("=" * 55)
    print()

    print("[1/3] 创建数据库...")
    await create_game_database(db_name)

    print("[2/3] 建表...")
    await create_game_tables(db_name)

    print("[3/3] 授权...")
    await grant_permissions(db_name)

    print()
    print("=" * 55)
    print(" ✅ 完成")
    print("=" * 55)
    print()
    print("下一步：")
    print(f"  在管理后台创建游戏项目：")
    print(f"    POST /admin/api/projects/")
    print(f"    {{")
    print(f'      "code_name":    "{code_name}",')
    print(f'      "display_name": "{display_name}",')
    print(f'      "db_name":      "{db_name}",')
    print(f'      "project_type": "game"')
    print(f"    }}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建游戏项目数据库")
    parser.add_argument("--code", required=True, help="游戏代码名（英文小写，如 yeya）")
    parser.add_argument("--name", default=None, help="显示名称（如 椰芽），默认同 code")
    args = parser.parse_args()

    code = args.code.lower().replace("-", "_")
    name = args.name or code
    asyncio.run(main(code, name))
