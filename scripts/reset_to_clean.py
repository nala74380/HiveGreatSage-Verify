r"""
文件位置: scripts/reset_to_clean.py
文件名称: reset_to_clean.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    开发期数据库与 Redis 清理脚本。

    当前用途:
      1. 清理开发 / 测试环境主库业务数据。
      2. 清理开发 / 测试环境游戏库业务数据。
      3. 清理 HiveGreatSage / Verify 相关 Redis key。
      4. 可选择保留 admin 表中的管理员账号。

    强安全边界:
      1. 本脚本禁止在 production / prod / release / online 环境运行。
      2. 本脚本默认不执行 Redis FLUSHALL。
      3. --yes 只跳过普通确认，不跳过环境保护。
      4. 如需 Redis FLUSHALL，必须额外传入 --redis-flushall，并输入二次确认短语。
      5. 本脚本不删除数据库本身，只清理 public schema 中的业务表数据。

运行示例:
    python scripts/reset_to_clean.py
    python scripts/reset_to_clean.py --keep-admin
    python scripts/reset_to_clean.py --yes --keep-admin
    python scripts/reset_to_clean.py --redis-flushall

环境要求:
    ENVIRONMENT 必须是 development / dev / local / test / testing 之一。

改进历史:
    V1.1.0 (2026-05-02) - 增加开发环境强保护；默认禁用 Redis FLUSHALL；增加数据库名保护。
    V1.0.0 - 初始全清脚本。
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


ALLOWED_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}
BLOCKED_ENVIRONMENTS = {"production", "prod", "release", "online", "staging"}

DEFAULT_ALLOWED_MAIN_DATABASES = {
    "hive_platform",
    "hive_platform_dev",
    "hive_verify_dev",
    "hive_test",
    "hive_test_platform",
}

PROTECTED_DATABASE_KEYWORDS = {
    "prod",
    "production",
    "release",
    "online",
    "live",
    "staging",
}

ALWAYS_KEEP_TABLES = {
    "alembic_version",
}

HGS_REDIS_KEY_PATTERNS = [
    "device:runtime:*",
    "heartbeat:*",
    "rate_limit:*",
    "refresh:*",
    "refresh_token:*",
    "blacklist:*",
    "token:*",
    "hgs:*",
    "verify:*",
    "hive:*",
]


@dataclass(frozen=True)
class ResetOptions:
    keep_admin: bool
    yes: bool
    include_redis: bool
    redis_flushall: bool


def _get_environment() -> str:
    value = (
        getattr(settings, "ENVIRONMENT", None)
        or getattr(settings, "APP_ENV", None)
        or os.getenv("ENVIRONMENT")
        or os.getenv("APP_ENV")
        or ""
    )
    return str(value).strip().lower()


def _require_safe_environment() -> None:
    environment = _get_environment()

    if not environment:
        raise RuntimeError(
            "未检测到 ENVIRONMENT / APP_ENV。"
            "为了防止误清库，请先在 .env 中设置 ENVIRONMENT=development。"
        )

    if environment in BLOCKED_ENVIRONMENTS:
        raise RuntimeError(
            f"当前环境为 {environment!r}，禁止执行 reset_to_clean.py。"
        )

    if environment not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            "当前环境不在允许列表中。"
            f"当前值：{environment!r}；允许值：{sorted(ALLOWED_ENVIRONMENTS)}。"
        )


def _get_allowed_main_databases() -> set[str]:
    raw = os.getenv("HGS_RESET_ALLOWED_MAIN_DBS", "")
    if not raw.strip():
        return set(DEFAULT_ALLOWED_MAIN_DATABASES)

    return {item.strip() for item in raw.split(",") if item.strip()}


def _database_name_from_url(database_url: str) -> str:
    return make_url(database_url).database or ""


def _assert_safe_main_database(database_name: str) -> None:
    if not database_name:
        raise RuntimeError("无法从 DATABASE_MAIN_URL 解析主库名称。")

    lowered = database_name.lower()

    if any(keyword in lowered for keyword in PROTECTED_DATABASE_KEYWORDS):
        raise RuntimeError(
            f"主库名称 {database_name!r} 命中生产保护关键词，禁止清理。"
        )

    allowed_databases = _get_allowed_main_databases()
    if database_name not in allowed_databases:
        raise RuntimeError(
            "主库名称不在允许清理列表中，禁止执行。"
            f" 当前主库：{database_name!r}；允许列表：{sorted(allowed_databases)}。\n"
            "如确认为开发库，可临时设置环境变量：\n"
            "HGS_RESET_ALLOWED_MAIN_DBS='hive_platform,你的开发库名'"
        )


def _assert_safe_game_database(database_name: str) -> None:
    if not database_name:
        raise RuntimeError("发现空游戏库名，禁止继续。")

    lowered = database_name.lower()

    if any(keyword in lowered for keyword in PROTECTED_DATABASE_KEYWORDS):
        raise RuntimeError(
            f"游戏库名称 {database_name!r} 命中生产保护关键词，禁止清理。"
        )

    if not lowered.startswith("hive_"):
        raise RuntimeError(
            f"游戏库名称 {database_name!r} 不以 hive_ 开头，禁止清理。"
        )


def _confirm_or_abort(options: ResetOptions, main_database_name: str) -> None:
    if options.yes:
        print("  WARN 已传入 --yes，跳过普通交互确认。")
        print("  WARN 环境保护、数据库名保护、Redis FLUSHALL 二次确认仍然生效。")
        return

    print()
    print("即将清理开发 / 测试环境数据。")
    print(f"主库：{main_database_name}")
    print(f"保留管理员账号：{'是' if options.keep_admin else '否'}")
    print(f"清理 Redis 项目 key：{'是' if options.include_redis else '否'}")
    print(f"Redis FLUSHALL：{'是' if options.redis_flushall else '否'}")
    print()
    confirm = input("请输入 RESET_TO_CLEAN 确认执行：").strip()

    if confirm != "RESET_TO_CLEAN":
        raise RuntimeError("确认短语不匹配，已取消。")


def _confirm_redis_flushall() -> None:
    print()
    print("DANGER 你正在请求 Redis FLUSHALL。")
    print("DANGER 这会清空当前 Redis 实例的所有数据库和所有 key。")
    print("DANGER 如果 Redis 不是 Verify 独占实例，会影响其他业务。")
    print()
    confirm = input("请输入 FLUSHALL_HGS_VERIFY 确认执行 Redis FLUSHALL：").strip()

    if confirm != "FLUSHALL_HGS_VERIFY":
        raise RuntimeError("Redis FLUSHALL 确认短语不匹配，已取消。")


def _make_engine_for_database(database_name: str):
    base_url = make_url(settings.DATABASE_MAIN_URL).set(database=database_name)
    return create_async_engine(base_url, echo=False, connect_args={"ssl": False})


def _quote_table_names(table_names: Iterable[str]) -> str:
    return ", ".join(f'"{name}"' for name in table_names)


async def _get_public_tables(engine) -> list[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename "
                "FROM pg_tables "
                "WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
        )
        return [row[0] for row in result.fetchall()]


async def _truncate_database_tables(
    database_name: str,
    *,
    keep_admin: bool,
    is_main_database: bool,
) -> None:
    engine = _make_engine_for_database(database_name)

    try:
        table_names = await _get_public_tables(engine)
        excluded_tables = set(ALWAYS_KEEP_TABLES)

        if keep_admin and is_main_database:
            excluded_tables.add("admin")

        tables_to_truncate = [
            table_name
            for table_name in table_names
            if table_name not in excluded_tables
        ]

        if not tables_to_truncate:
            print(f"  INFO 数据库 {database_name} 没有需要清理的业务表。")
            return

        quoted_tables = _quote_table_names(tables_to_truncate)

        async with engine.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE")
            )

        print(f"  OK 数据库 {database_name} 已清理。")
        print(f"     清理表数：{len(tables_to_truncate)}")
        if excluded_tables:
            print(f"     保留表：{', '.join(sorted(excluded_tables))}")

    finally:
        await engine.dispose()


async def _get_game_database_names(main_database_name: str) -> list[str]:
    engine = _make_engine_for_database(main_database_name)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT DISTINCT db_name "
                    "FROM game_project "
                    "WHERE db_name IS NOT NULL AND db_name <> '' "
                    "ORDER BY db_name"
                )
            )
            database_names = [row[0] for row in result.fetchall()]
    finally:
        await engine.dispose()

    safe_names: list[str] = []
    for database_name in database_names:
        _assert_safe_game_database(database_name)
        safe_names.append(database_name)

    return safe_names


def _get_redis_url() -> str | None:
    return (
        getattr(settings, "REDIS_URL", None)
        or os.getenv("REDIS_URL")
        or os.getenv("HGS_REDIS_URL")
    )


async def _delete_redis_keys_by_patterns(patterns: list[str]) -> int:
    redis_url = _get_redis_url()
    if not redis_url:
        print("  WARN 未配置 REDIS_URL，跳过 Redis 清理。")
        return 0

    try:
        import redis.asyncio as redis
    except ImportError:
        print("  WARN 未安装 redis Python 包，跳过 Redis 清理。")
        return 0

    client = redis.from_url(redis_url, decode_responses=True)

    deleted_total = 0
    try:
        for pattern in patterns:
            batch: list[str] = []

            async for key in client.scan_iter(match=pattern, count=500):
                batch.append(key)

                if len(batch) >= 500:
                    deleted_total += await client.delete(*batch)
                    batch.clear()

            if batch:
                deleted_total += await client.delete(*batch)

        return deleted_total

    finally:
        await client.aclose()


async def _flush_all_redis() -> None:
    redis_url = _get_redis_url()
    if not redis_url:
        print("  WARN 未配置 REDIS_URL，跳过 Redis FLUSHALL。")
        return

    try:
        import redis.asyncio as redis
    except ImportError:
        print("  WARN 未安装 redis Python 包，跳过 Redis FLUSHALL。")
        return

    client = redis.from_url(redis_url, decode_responses=True)

    try:
        await client.flushall()
    finally:
        await client.aclose()


async def reset_to_clean(options: ResetOptions) -> None:
    _require_safe_environment()

    main_database_name = _database_name_from_url(settings.DATABASE_MAIN_URL)
    _assert_safe_main_database(main_database_name)

    _confirm_or_abort(options, main_database_name)

    if options.redis_flushall:
        _confirm_redis_flushall()

    print()
    print("=" * 60)
    print(" HiveGreatSage-Verify 开发 / 测试环境清理")
    print("=" * 60)
    print()

    print("[1/3] 清理主库业务表...")
    await _truncate_database_tables(
        main_database_name,
        keep_admin=options.keep_admin,
        is_main_database=True,
    )

    print()
    print("[2/3] 清理游戏库业务表...")
    game_database_names = await _get_game_database_names(main_database_name)

    if not game_database_names:
        print("  INFO 未发现 game_project.db_name，跳过游戏库清理。")
    else:
        for game_database_name in game_database_names:
            await _truncate_database_tables(
                game_database_name,
                keep_admin=False,
                is_main_database=False,
            )

    print()
    print("[3/3] 清理 Redis...")
    if not options.include_redis:
        print("  INFO 已按参数跳过 Redis 清理。")
    elif options.redis_flushall:
        await _flush_all_redis()
        print("  OK Redis FLUSHALL 已执行。")
    else:
        deleted_count = await _delete_redis_keys_by_patterns(HGS_REDIS_KEY_PATTERNS)
        print("  OK Redis 项目相关 key 已清理。")
        print(f"     删除 key 数：{deleted_count}")

    print()
    print("=" * 60)
    print(" OK 清理完成")
    print("=" * 60)
    print()
    print("后续建议：")
    print("  1. 运行 Alembic 确认主库迁移状态。")
    print("  2. 重新运行 scripts/init_data.py 创建管理员。")
    print("  3. 通过后台 API 创建项目、代理和用户。")
    print("  4. 启动 Web / Redis / Celery Worker / Celery Beat 后再联调。")


def _parse_args() -> ResetOptions:
    parser = argparse.ArgumentParser(
        description="清理 HiveGreatSage-Verify 开发 / 测试环境数据。"
    )

    parser.add_argument(
        "--keep-admin",
        action="store_true",
        help="清理主库时保留 admin 表。",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过普通确认。环境保护和 Redis FLUSHALL 二次确认不会被跳过。",
    )

    parser.add_argument(
        "--no-redis",
        action="store_true",
        help="跳过 Redis 清理。",
    )

    parser.add_argument(
        "--redis-flushall",
        action="store_true",
        help="危险操作：执行 Redis FLUSHALL。默认不会执行。",
    )

    args = parser.parse_args()

    return ResetOptions(
        keep_admin=args.keep_admin,
        yes=args.yes,
        include_redis=not args.no_redis,
        redis_flushall=args.redis_flushall,
    )


def main() -> None:
    options = _parse_args()

    try:
        asyncio.run(reset_to_clean(options))
    except Exception as exc:
        print()
        print("ERROR 清理已中止。")
        print(f"原因：{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()