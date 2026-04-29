"""add max_devices to user table

Revision ID: 0003_add_user_max_devices
Revises: 0002_add_user_level_check
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa

revision = '0003_add_user_max_devices'
down_revision = '0002_add_user_level_check'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column(
            'max_devices',
            sa.Integer(),
            nullable=False,
            server_default='500',
            comment='设备绑定上限，独立设置，不由级别自动决定',
        ),
    )


def downgrade() -> None:
    op.drop_column('user', 'max_devices')
