"""add user token_version

Revision ID: 0020_user_token_version
Revises: 0019_login_log_device_id_index
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_user_token_version"
down_revision = "0019_login_log_device_id_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="用户 Token 版本号；递增后旧 AT/RT 立即失效",
        ),
    )
    op.create_check_constraint(
        "chk_user_token_version_non_negative",
        "user",
        "token_version >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_user_token_version_non_negative",
        "user",
        type_="check",
    )
    op.drop_column("user", "token_version")
