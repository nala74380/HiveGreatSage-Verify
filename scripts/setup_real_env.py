r"""
文件位置: scripts/setup_real_env.py
名称: 真机测试环境初始化脚本
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.1.0
功能说明:
    仅做两件事：
      1. 主库建表（确保所有表结构存在）
      2. 创建第一个管理员账号（幂等）

    其他所有操作（游戏项目、代理、用户）全部通过前台 Swagger UI 操作。

运行方式：python scripts/setup_real_env.py

改进历史:
    V1.1.0 (2026-04-28) - 精简为只建表 + 建管理员，其余全走前台
    V1.0.0 - 包含游戏项目库创建（已移除）
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.security import hash_password
from app.database import Base, _main_engine, _main_session_factory
from app.models.main.models import Admin


# ═══════════════════════════════════════════════════════════════
# ⚠️ 运行前修改管理员密码
# ═══════════════════════════════════════════════════════════════
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@2026!"   # ← 改为强密码
# ═══════════════════════════════════════════════════════════════


async def main() -> None:
    print("=" * 50)
    print(" HiveGreatSage-Verify 环境初始化")
    print("=" * 50)

    # 1. 主库建表
    print("\n[1/2] 主库建表...")
    async with _main_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✅ 建表完成")

    # 2. 创建管理员
    print("\n[2/2] 创建管理员账号...")
    async with _main_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :u"),
            {"u": ADMIN_USERNAME},
        )
        if result.scalar():
            print(f"  ℹ️  管理员 '{ADMIN_USERNAME}' 已存在，跳过")
        else:
            session.add(Admin(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                status="active",
            ))
            await session.commit()
            print(f"  ✅ 管理员创建成功：{ADMIN_USERNAME} / {ADMIN_PASSWORD}")

    await _main_engine.dispose()

    print()
    print("=" * 50)
    print(" ✅ 初始化完成")
    print("=" * 50)
    print()
    print("打开 Swagger UI 继续操作：")
    print("  http://127.0.0.1:8000/docs")
    print()
    print("  1. POST /admin/api/auth/login      → 管理员登录")
    print("  2. POST /admin/api/projects/        → 创建游戏项目")
    print("  3. POST /api/agents/                → 创建代理")
    print("  4. POST /api/agents/auth/login      → 代理登录")
    print("  5. POST /api/users/                 → 代理创建用户")
    print("  6. POST /api/users/{id}/authorizations → 授权用户")


if __name__ == "__main__":
    asyncio.run(main())
