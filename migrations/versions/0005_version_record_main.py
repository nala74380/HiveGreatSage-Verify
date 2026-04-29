"""add version_record to main database

Revision ID: 0006_version_record_main
Revises: 0005_add_imsi_to_device_binding
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_version_record_main'
down_revision = '0005_add_imsi_to_device_binding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'version_record',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('game_project_id', sa.Integer(),
                  sa.ForeignKey('game_project.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('client_type', sa.String(10), nullable=False,
                  comment='pc | android'),
        sa.Column('version', sa.String(20), nullable=False,
                  comment='MAJOR.MINOR.PATCH'),
        sa.Column('package_path', sa.String(500), nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=True),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('force_update', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default='true'),
        sa.Column('released_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('game_project_id', 'client_type', 'version',
                            name='uq_project_client_version'),
    )
    op.create_index(
        'idx_version_record_project_client',
        'version_record',
        ['game_project_id', 'client_type', 'is_active'],
    )


def downgrade() -> None:
    op.drop_index('idx_version_record_project_client', 'version_record')
    op.drop_table('version_record')
