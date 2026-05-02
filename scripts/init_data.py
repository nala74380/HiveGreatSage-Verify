r"""
文件位置: scripts/init_data.py
文件名称: init_data.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.2.0
功能说明:
    数据库初始化脚本。
    仅创建第一个管理员账号。

    当前边界:
      1. 本脚本不创建游戏项目。
      2. 本脚本不创建代理账号。
      3. 本脚本不创建用户账号。
      4. 本脚本不创建演示数据。
      5. 游戏项目、代理账号、用户账号应通过管理后台 API 创建。

    安全要求:
      1. 不允许在源码中硬编码默认管理员密码。
      2. 不允许在终端输出管理员密码。
      3. 开发期可通过环境变量或交互式输入提供初始密码。

运行方式:
    python scripts/init_data.py

可选环境变量:
    HGS_INIT_ADMIN_USERNAME
    HGS_INIT_ADMIN_PASSWORD

示例:
    HGS_INIT_ADMIN_USERNAME=admin HGS_INIT_ADMIN_PASSWORD='your-strong-password' python scripts/init_data.py

幂等性:
    管理员已存在则跳过，不会重复创建。

改进历史:
    V1.2.0 (2026-05-02) - 移除默认管理员密码硬编码；禁止打印密码；支持环境变量和交互式输入。
    V1.1.0 (2026-04-28) - 移除演示数据，只建管理员账号。
    V1.0.1 - 修复 Windows asyncpg SSL 问题。
    V1.0.0 - 初始版本。

调试信息:
    运行前确认 .env 配置正确，PostgreSQL 和 Redis 服务正在运行。
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.security import hash_password
from app.database import _main_engine, _main_session_factory
from app.models.main.models import Admin


MIN_ADMIN_PASSWORD_LENGTH = 12


def _read_admin_username() -> str:
    username = os.getenv("HGS_INIT_ADMIN_USERNAME", "").strip()
    if username:
        return username
    return "admin"


def _validate_admin_password(password: str) -> None:
    if not password:
        raise ValueError("初始管理员密码不能为空。")

    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(
            f"初始管理员密码长度不能少于 {MIN_ADMIN_PASSWORD_LENGTH} 位。"
        )


def _read_admin_password() -> str:
    env_password = os.getenv("HGS_INIT_ADMIN_PASSWORD", "")
    if env_password:
        _validate_admin_password(env_password)
        return env_password

    if not sys.stdin.isatty():
        raise RuntimeError(
            "未提供初始管理员密码。请设置环境变量 HGS_INIT_ADMIN_PASSWORD 后再运行。"
        )

    password = getpass.getpass("请输入初始管理员密码（不会回显）：")
    confirm_password = getpass.getpass("请再次输入初始管理员密码：")

    if password != confirm_password:
        raise ValueError("两次输入的初始管理员密码不一致。")

    _validate_admin_password(password)
    return password


async def create_admin() -> None:
    admin_username = _read_admin_username()

    async with _main_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :username"),
            {"username": admin_username},
        )
        existing_id = result.scalar()

        if existing_id:
            print(f"  INFO 管理员 '{admin_username}' 已存在（id={existing_id}），跳过。")
            return

        admin_password = _read_admin_password()

        admin = Admin(
            username=admin_username,
            password_hash=hash_password(admin_password),
            status="active",
        )
        session.add(admin)
        await session.commit()

        print("  OK 管理员创建成功。")
        print(f"     用户名：{admin_username}")
        print("     密码：已设置，出于安全原因不显示。")
        print("  WARN 请首次登录后立即按项目安全规范轮换密码。")


async def main() -> None:
    print("=" * 55)
    print(" HiveGreatSage-Verify 数据库初始化")
    print("=" * 55)
    print()
    print("[1/1] 创建管理员账号...")
    await create_admin()
    print()
    print("=" * 55)
    print(" OK 初始化完成")
    print("=" * 55)
    print()
    print("下一步：")
    print("  1. 管理员登录后台：POST /admin/api/auth/login")
    print("  2. 创建游戏项目：POST /admin/api/projects/")
    print("  3. 创建代理账号：POST /api/agents/")
    print("  4. 代理创建用户：POST /api/users/")
    print()
    await _main_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())