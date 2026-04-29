r"""
文件位置: migrations/versions/0002_add_user_level_check.py
文件名称: 0002_add_user_level_check.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    为 user 表的 user_level 字段添加数据库层 CHECK 约束，
    确保只能写入合法的用户级别枚举值。
改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from alembic import op

revision: str = "0002_add_user_level_check"
down_revision: str = "a458709e354f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        constraint_name="chk_user_level_enum",
        table_name="user",
        condition="user_level IN ('trial', 'normal', 'vip', 'svip', 'tester')",
    )


def downgrade() -> None:
    op.drop_constraint(
        constraint_name="chk_user_level_enum",
        table_name="user",
        type_="check",
    )