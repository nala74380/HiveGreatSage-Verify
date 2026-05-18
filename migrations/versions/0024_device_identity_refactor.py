"""device identity refactor and remove IMSI fields

Revision ID: 0024_device_identity_refactor
Revises: 0023_authorization_freeze_record
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_device_identity_refactor"
down_revision = "0023_authorization_freeze_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_binding",
        sa.Column(
            "connection_type",
            sa.String(length=16),
            nullable=True,
            comment="连接类型：usb / tcp / unknown",
        ),
    )
    op.add_column(
        "device_binding",
        sa.Column(
            "connection_label",
            sa.String(length=255),
            nullable=True,
            comment="连接标识展示串：USB 显示 SN，TCP 显示 IP:端口",
        ),
    )
    op.drop_index("idx_device_binding_imsi_hash", table_name="device_binding")
    op.drop_column("device_binding", "imsi_hash")
    op.drop_column("device_binding", "imsi")


def downgrade() -> None:
    op.add_column(
        "device_binding",
        sa.Column(
            "imsi",
            sa.String(length=256),
            nullable=True,
            comment="设备 IMSI 码（Fernet 加密存储）；通过 imsi_hash 反查定位后解密读取",
        ),
    )
    op.add_column(
        "device_binding",
        sa.Column(
            "imsi_hash",
            sa.String(length=64),
            nullable=True,
            comment="IMSI HMAC-SHA256 哈希；用于非明文关联排障与加密反查索引",
        ),
    )
    op.create_index("idx_device_binding_imsi_hash", "device_binding", ["imsi_hash"])
    op.drop_column("device_binding", "connection_label")
    op.drop_column("device_binding", "connection_type")
