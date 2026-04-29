r"""
文件位置: scripts/reset_to_clean.py
名称: 数据库全清重置脚本
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.0.0
功能说明:
    将 hive_platform 主库和所有游戏项目库重置为干净初始状态。
    清除所有用户、代理、授权、设备绑定、登录日志、游戏数据。
    保留：表结构、管理员账号（可选）。
    同步清除 Redis 所有缓存数据。

    ⚠️ 高危操作，不可逆！
    运行前会显示当前数据量让你确认，输入 YES 才执行。

运行方式：
    python scripts/reset_to_clean.py
    python scripts/reset_to_clean.py --keep-admin   # 保留管理员账号
    python scripts/reset_to_clean.py --yes          # 跳过确认（自动化场景）
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# ─────────────────────────────────────────────────────────────
# 主库表清理顺序（必须尊重外键依赖，子表先删）
# ─────────────────────────────────────────────────────────────
# login_log          → 无外键约束问题，先删
# device_binding     → 依赖 user
# authorization      → 依赖 user、game_project
# agent_project_auth → 依赖 agent、game_project
# version_record     → 依赖 game_project
# user               → 依赖 agent（created_by_agent_id）
# agent              → 自引用，需按 level 倒序或直接禁用外键检查
# game_project       → 被多个表依赖，最后删
# admin              → 可选保留

TRUNCATE_ORDER = [
    "login_log",
    "device_binding",
    '"authorization"',       # authorization 是 PostgreSQL 保留字，必须加引号
    "agent_project_auth",
    "version_record",
    '"user"',               # user 也是保留字
    "agent",
    "game_project",
]

# 游戏库表（每个游戏库都要清）
GAME_TABLE_ORDER = [
    "user_script_param",
    "device_runtime",
    "version_record",    # 游戏库也有 version_record
    "script_param_def",
    "project_config",
]


async def get_stats(engine) -> dict:
    """获取当前各表数据量（用于确认提示）。"""
    stats = {}
    async with engine.connect() as conn:
        for table in ["admin", "agent", '"user"', "game_project",
                      "authorization", "device_binding", "login_log",
                      "agent_project_auth", "version_record"]:
            try:
                r = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                stats[table.strip('"')] = r.scalar()
            except Exception:
                stats[table.strip('"')] = "表不存在"
    return stats


async def get_game_databases(engine) -> list[str]:
    """查询主库中注册的所有游戏项目库名。"""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT db_name FROM game_project WHERE db_name IS NOT NULL")
        )
        return [row[0] for row in result.all() if row[0]]


async def clear_main_db(engine, keep_admin: bool) -> None:
    """清空主库所有数据表（按外键顺序）。"""
    # 使用 TRUNCATE ... CASCADE 一次性清所有表，忽略外键顺序问题
    tables = list(TRUNCATE_ORDER)
    if keep_admin:
        tables = [t for t in tables if t != "admin"]

    async with engine.begin() as conn:
        # RESTART IDENTITY 重置序列（ID 从 1 重新开始）
        # CASCADE 自动处理外键依赖
        truncate_sql = ", ".join(tables)
        await conn.execute(
            text(f"TRUNCATE TABLE {truncate_sql} RESTART IDENTITY CASCADE")
        )
    print("  ✅ 主库数据已清空（表结构保留）")
    if keep_admin:
        print("  ℹ️  管理员账号已保留（--keep-admin）")


async def clear_game_db(db_name: str) -> None:
    """清空一个游戏项目库的所有数据表。"""
    game_url = make_url(settings.DATABASE_MAIN_URL).set(database=db_name)
    engine = create_async_engine(game_url, echo=False, connect_args={"ssl": False})
    try:
        async with engine.begin() as conn:
            # 查询该库中实际存在的表
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            ))
            existing_tables = [row[0] for row in result.all()]

            if not existing_tables:
                print(f"  ℹ️  {db_name} 库为空，跳过")
                return

            tables_sql = ", ".join(existing_tables)
            await conn.execute(
                text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE")
            )
        print(f"  ✅ 游戏库 {db_name} 数据已清空")
    except Exception as e:
        print(f"  ⚠️  游戏库 {db_name} 清理失败: {e}")
    finally:
        await engine.dispose()


async def clear_redis() -> None:
    """清空 Redis 全部数据（FLUSHALL）。"""
    import redis.asyncio as aioredis
    r = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.flushall()
        print("  ✅ Redis 全部数据已清空")
    except Exception as e:
        print(f"  ⚠️  Redis 清理失败: {e}")
    finally:
        await r.aclose()


async def main(keep_admin: bool, auto_yes: bool) -> None:
    print()
    print("=" * 60)
    print(" ⚠️  HiveGreatSage-Verify 数据库全清重置")
    print("=" * 60)
    print()

    # 连接主库
    engine = create_async_engine(
        settings.DATABASE_MAIN_URL, echo=False, connect_args={"ssl": False}
    )

    # 显示当前数据量
    print("当前数据量：")
    try:
        stats = await get_stats(engine)
        print(f"  管理员    : {stats.get('admin', '—')} 条")
        print(f"  代理      : {stats.get('agent', '—')} 条")
        print(f"  用户      : {stats.get('user', '—')} 条")
        print(f"  游戏项目  : {stats.get('game_project', '—')} 条")
        print(f"  授权记录  : {stats.get('authorization', '—')} 条")
        print(f"  设备绑定  : {stats.get('device_binding', '—')} 条")
        print(f"  登录日志  : {stats.get('login_log', '—')} 条")
    except Exception as e:
        print(f"  （无法读取数据量：{e}）")

    # 查询游戏库列表
    game_dbs = []
    try:
        game_dbs = await get_game_databases(engine)
        if game_dbs:
            print(f"\n  游戏库列表：{', '.join(game_dbs)}")
    except Exception:
        pass

    print()
    print("清理范围：")
    print("  • 主库 hive_platform 全部数据")
    for db in game_dbs:
        print(f"  • 游戏库 {db} 全部数据")
    print("  • Redis 全部缓存")
    if keep_admin:
        print("  （✓ 管理员账号将被保留）")
    else:
        print("  （⚠️  管理员账号也将被清除）")

    print()

    if not auto_yes:
        confirm = input("输入 YES 确认执行（其他任何输入取消）: ").strip()
        if confirm != "YES":
            print("\n已取消，数据未修改。")
            await engine.dispose()
            return

    print()
    print("开始清理...")

    # 清主库
    print("\n[1] 清空主库数据...")
    await clear_main_db(engine, keep_admin=keep_admin)

    # 清游戏库
    if game_dbs:
        print(f"\n[2] 清空游戏库数据（共 {len(game_dbs)} 个）...")
        for db in game_dbs:
            await clear_game_db(db)
    else:
        print("\n[2] 无游戏库需要清理")

    # 清 Redis
    print("\n[3] 清空 Redis...")
    await clear_redis()

    await engine.dispose()

    print()
    print("=" * 60)
    print(" ✅ 重置完成！数据库已恢复干净初始状态。")
    print("=" * 60)
    print()
    print("下一步：重新运行初始化脚本")
    print("  python scripts/setup_real_env.py")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据库全清重置")
    parser.add_argument(
        "--keep-admin",
        action="store_true",
        help="保留管理员账号（清除其他所有数据）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过确认提示，直接执行（危险！）",
    )
    args = parser.parse_args()
    asyncio.run(main(keep_admin=args.keep_admin, auto_yes=args.yes))
