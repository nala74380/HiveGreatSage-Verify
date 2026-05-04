"""remove legacy authorization fields from user

Revision ID: 0016_user_legacy_fields
Revises: 0015_system_setting
Create Date: 2026-05-03

User is now only the account principal. Authorization-level facts live on
authorization: user_level, authorized_devices, and valid_until.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0016_user_legacy_fields"
down_revision = "0015_system_setting"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("user", "user_level"):
        op.drop_column("user", "user_level")
    if _has_column("user", "max_devices"):
        op.drop_column("user", "max_devices")
    if _has_column("user", "expired_at"):
        op.drop_column("user", "expired_at")


def downgrade() -> None:
    if not _has_column("user", "user_level"):
        op.add_column(
            "user",
            sa.Column("user_level", sa.String(length=20), nullable=False, server_default="normal"),
        )
    if not _has_column("user", "max_devices"):
        op.add_column(
            "user",
            sa.Column("max_devices", sa.Integer(), nullable=False, server_default="500"),
        )
    if not _has_column("user", "expired_at"):
        op.add_column(
            "user",
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        )
