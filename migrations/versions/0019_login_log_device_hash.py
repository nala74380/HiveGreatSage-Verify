r"""
文件位置: migrations/versions/0019_login_log_device_hash.py
文件名称: 0019_login_log_device_hash.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    登录日志 login_log 增加 device_fingerprint_hash 字段，并清空历史 device_fingerprint 原文。

设计目标:
    - LoginLog 用 hash 支持排障关联。
    - LoginLog 不再继续保存设备指纹原文。
    - 设备指纹原文仅保留在 DeviceBinding 等业务闭环必要表内。

注意:
    - 历史 device_fingerprint 原文会被清空。
    - 历史记录无法在迁移中可靠补 HMAC hash，因为 HMAC key 来自应用 SECRET_KEY。
    - 新登录日志由应用层写入 device_fingerprint_hash。
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_login_log_hash"
down_revision = "0018_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "login_log",
        sa.Column(
            "device_fingerprint_hash",
            sa.String(length=64),
            nullable=True,
            comment="设备指纹 HMAC-SHA256 哈希，用于非明文关联排障",
        ),
    )
    op.create_index(
        "idx_login_log_device_hash",
        "login_log",
        ["device_fingerprint_hash"],
    )

    # 开发期清理策略：不再保留历史登录日志中的设备指纹原文。
    op.execute("UPDATE login_log SET device_fingerprint = NULL WHERE device_fingerprint IS NOT NULL")


def downgrade() -> None:
    op.drop_index("idx_login_log_device_hash", table_name="login_log")
    op.drop_column("login_log", "device_fingerprint_hash")
