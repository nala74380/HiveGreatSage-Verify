"""remove login_log hash and device binding connection fields

Revision ID: 0025_identity_cleanup
Revises: 0024_device_identity_refactor
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_identity_cleanup"
down_revision = "0024_device_identity_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    login_log_columns = {col["name"] for col in inspector.get_columns("login_log")}
    if "device_fingerprint_hash" in login_log_columns:
        op.drop_column("login_log", "device_fingerprint_hash")

    device_binding_columns = {col["name"] for col in inspector.get_columns("device_binding")}
    if "connection_label" in device_binding_columns:
        op.drop_column("device_binding", "connection_label")
    if "connection_type" in device_binding_columns:
        op.drop_column("device_binding", "connection_type")


def downgrade() -> None:
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
            comment="连接标识展示串：USB 显示 SN；TCP 显示 IP:端口",
        ),
    )
    op.add_column(
        "login_log",
        sa.Column(
            "device_fingerprint_hash",
            sa.String(length=64),
            nullable=True,
            comment="历史兼容字段，当前主链不再使用",
        ),
    )
