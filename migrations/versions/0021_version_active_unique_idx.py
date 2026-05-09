"""add partial unique index on version_record (one active per project per client_type)

Revision ID: 0021_version_active_unique_idx
Revises: 0020_user_token_version
Create Date: 2026-05-09
"""

from alembic import op


revision = "0021_version_active_unique_idx"
down_revision = "0020_user_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_version_record_active_per_project_client",
        "version_record",
        ["game_project_id", "client_type"],
        unique=True,
        postgresql_where="is_active IS TRUE",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_version_record_active_per_project_client",
        table_name="version_record",
        postgresql_where="is_active IS TRUE",
    )
