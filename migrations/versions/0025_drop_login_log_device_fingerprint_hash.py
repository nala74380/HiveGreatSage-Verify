"""drop login_log device_fingerprint_hash

Revision ID: 0025_loginlog_fp_cleanup
Revises: 0024_device_identity_refactor
Create Date: 2026-05-18
"""

from alembic import op


revision = "0025_loginlog_fp_cleanup"
down_revision = "0024_device_identity_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("login_log", "device_fingerprint_hash")


def downgrade() -> None:
    from sqlalchemy import Column, String

    op.add_column(
        "login_log",
        Column(
            "device_fingerprint_hash",
            String(length=64),
            nullable=True,
            comment="历史兼容字段，当前主链不再使用",
        ),
    )
