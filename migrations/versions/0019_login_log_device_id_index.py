r"""
文件位置: migrations/versions/0019_login_log_device_id_index.py
文件名称: 0019_login_log_device_id_index.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    登录日志 login_log 增加 device_id 查询索引。
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_login_log_device_id_index"
down_revision = "0018_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_login_log_device_id",
        "login_log",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_login_log_device_id", table_name="login_log")
