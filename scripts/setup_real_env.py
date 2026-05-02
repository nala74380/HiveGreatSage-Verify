r"""
文件位置: scripts/setup_real_env.py
文件名称: setup_real_env.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-02
版本: V1.2.0
功能说明:
    开发 / 真机测试环境初始化脚本。

    当前仅做两件事:
      1. 确保主库表结构存在。
      2. 创建第一个管理员账号。

    重要边界:
      1. 本脚本使用 Base.metadata.create_all()，不等同于 Alembic 迁移。
      2. 生产环境不得用本脚本替代 Alembic 版本治理。
      3. 游戏项目、代理账号、用户账号应通过后台 API 创建。
      4. 本脚本不创建演示数据。

    安全要求:
      1. 不允许在源码中硬编码默认管理员密码。
      2. 不允许在终端输出管理员密码。
      3. 开发期可通过环境变量或交互式输入提供初始密码。

运行方式:
    python scripts/setup_real_env.py

可选环境变量:
    HGS_INIT_ADMIN_USERNAME
    HGS_INIT_ADMIN_PASSWORD

示例:
    HGS_INIT_ADMIN_USERNAME=admin HGS_INIT_ADMIN_PASSWORD='your-strong-password' python scripts/setup_real_env.py

改进历史:
    V1.2.0 (2026-05-02) - 移除默认管理员密码硬编码；禁止打印密码；支持环境变量和交互式输入。
    V1.1.0 (2026-04-28) - 精简为只建表 + 建管理员，其余全走前台。
    V1.0.0 - 包含游戏项目库创建，已移除。
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.security import hash_password
from app.database import Base, _main_engine, _main_session_factory
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


async def ensure_main_tables() -> None:
    print("[1/2] 确保主库表结构存在...")
    async with _main_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  OK 主库表结构已确认。")


async def create_admin() -> None:
    print("[2/2] 创建管理员账号...")

    admin_username = _read_admin_username()

    async with _main_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM admin WHERE username = :username"),
            {"username": admin_username},
        )
        existing_id = result.scalar()

        if existing_id:
            print(f"  INFO 管理员 '{admin_username}' 已存在，跳过。")
            return

        admin_password = _read_admin_password()

        session.add(
            Admin(
                username=admin_username,
                password_hash=hash_password(admin_password),
                status="active",
            )
        )
        await session.commit()

        print("  OK 管理员创建成功。")
        print(f"     用户名：{admin_username}")
        print("     密码：已设置，出于安全原因不显示。")
        print("  WARN 请首次登录后立即按项目安全规范轮换密码。")


async def main() -> None:
    print("=" * 50)
    print(" HiveGreatSage-Verify 开发 / 真机测试环境初始化")
    print("=" * 50)
    print()
    print("WARN 本脚本不能替代生产 Alembic 迁移流程。")
    print()

    await ensure_main_tables()
    print()
    await create_admin()
    print()

    await _main_engine.dispose()

    print("=" * 50)
    print(" OK 初始化完成")
    print("=" * 50)
    print()
    print("打开 Swagger UI 继续操作：")
    print("  http://127.0.0.1:8000/docs")
    print()
    print("建议顺序：")
    print("  1. POST /admin/api/auth/login            -> 管理员登录")
    print("  2. POST /admin/api/projects/             -> 创建游戏项目")
    print("  3. POST /api/agents/                     -> 创建代理")
    print("  4. POST /api/agents/auth/login           -> 代理登录")
    print("  5. POST /api/users/                      -> 代理创建用户")
    print("  6. POST /api/users/{id}/authorizations   -> 授权用户")


if __name__ == "__main__":
    asyncio.run(main())