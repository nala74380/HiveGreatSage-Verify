"""add imsi to device binding

Revision ID: 0005_add_imsi_to_device_binding
Revises: 0004_project_type_and_agent_auth
Create Date: 2026-04-25

T027: 接入契约 §8 — IMSI 改为登录成功后单独上传。
在 device_binding 表新增 imsi 字段（可空），存储设备 IMSI 码。
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_add_imsi_to_device_binding"
down_revision = "0004_project_type_and_agent_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_binding",
        sa.Column("imsi", sa.String(64), nullable=True, comment="设备 IMSI 码，登录成功后单独上传"),
    )


def downgrade() -> None:
    op.drop_column("device_binding", "imsi")
