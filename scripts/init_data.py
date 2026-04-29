r"""
文件位置: scripts/init_data.py
文件名称: init_data.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-18
版本: V1.1.0
功能说明:
    数据库初始化脚本 — 仅创建第一个管理员账号。

    ⚠️ 本脚本不再创建任何演示/测试数据。
       游戏项目、代理账号、用户账号，全部通过管理后台 API 创建。

    运行方式：python scripts/init_data.py
    幂等性：管理员已存在则跳过，不会重复创建。

    游戏项目数据库（hive_game_{code_name}）需要单独创建。
    请使用 scripts/setup_game_db.py 创建游戏项目及独立库。

改进历史:
    V1.1.0 (2026-04-28) - 移除演示数据（测试游戏/测试用户），只建管理员账号；
                          不再自动创建游戏项目库（改为按需操作）
    V1.0.1 - 修复 Windows asyncpg SSL 问题
    V1.0.0 - 初始版本
调试信息:
    运行前确认 .env 配置正确，PostgreSQL 和 Redis 服务正在运行。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.security import hash_password
from app.database import _main_engine, _main_session_factory
from app.models.main.models import Admin

# ═══════════════════════════════════════════════════════════════
# ⚠️ 在此填写管理员账号信息（运行前修改）
# ═══════════════════════════════════════════════════════════════
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@2026!"   # ← 必须修改为强密码
# ═══════════════════════════════════════════════════════════════


async def create_admin() -> None:
    async with _main_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :u"),
            {"u": ADMIN_USERNAME},
        )
        existing_id = result.scalar()

        if existing_id:
            print(f"  ℹ️  管理员 '{ADMIN_USERNAME}' 已存在（id={existing_id}），跳过")
        else:
            admin = Admin(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                status="active",
            )
            session.add(admin)
            await session.commit()
            print(f"  ✅ 管理员创建成功")
            print(f"     用户名：{ADMIN_USERNAME}")
            print(f"     密　码：{ADMIN_PASSWORD}")
            print()
            print("  ⚠️  请立即登录管理后台修改密码！")


async def main() -> None:
    print("=" * 55)
    print(" HiveGreatSage-Verify 数据库初始化")
    print("=" * 55)
    print()
    print("[1/1] 创建管理员账号...")
    await create_admin()
    print()
    print("=" * 55)
    print(" ✅ 初始化完成")
    print("=" * 55)
    print()
    print("下一步：")
    print("  1. 用管理员账号登录后台：POST /admin/api/auth/login")
    print("  2. 创建游戏项目：POST /admin/api/projects/")
    print("  3. 创建代理账号：POST /api/agents/")
    print("  4. 代理创建用户：POST /api/users/")
    print()
    await _main_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
