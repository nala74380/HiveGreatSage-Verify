"""add authorization freeze record

Revision ID: 0023_authorization_freeze_record
Revises: 0022_device_binding_imsi_encrypt
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_authorization_freeze_record"
down_revision = "0022_device_binding_imsi_encrypt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_freeze_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("freeze_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="frozen", nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_by_agent_id", sa.Integer(), nullable=True),
        sa.Column("frozen_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("original_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remaining_hours", sa.Integer(), nullable=True),
        sa.Column(
            "estimated_remaining_points",
            sa.Numeric(18, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_agent_id", sa.Integer(), nullable=True),
        sa.Column("released_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("new_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("refund_document_id", sa.BigInteger(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "freeze_type IN ('agent_suspend', 'admin_suspend')",
            name="ck_authorization_freeze_type",
        ),
        sa.CheckConstraint(
            "status IN ('frozen', 'released', 'refunded', 'cancelled')",
            name="ck_authorization_freeze_status",
        ),
        sa.CheckConstraint(
            "remaining_hours IS NULL OR remaining_hours >= 0",
            name="ck_authorization_freeze_remaining_hours_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_remaining_points >= 0",
            name="ck_authorization_freeze_estimated_points_non_negative",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agent.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorization_id"], ["authorization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["frozen_by_admin_id"], ["admin.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["frozen_by_agent_id"], ["agent.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["game_project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["refund_document_id"], ["accounting_document.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by_admin_id"], ["admin.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by_agent_id"], ["agent.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["settled_by_admin_id"], ["admin.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_authorization_freeze_authorization",
        "authorization_freeze_record",
        ["authorization_id"],
    )
    op.create_index(
        "idx_authorization_freeze_agent",
        "authorization_freeze_record",
        ["agent_id", "frozen_at"],
    )
    op.create_index(
        "idx_authorization_freeze_user_project",
        "authorization_freeze_record",
        ["user_id", "project_id"],
    )
    op.create_index(
        "idx_authorization_freeze_status",
        "authorization_freeze_record",
        ["status", "frozen_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_authorization_freeze_status", table_name="authorization_freeze_record")
    op.drop_index("idx_authorization_freeze_user_project", table_name="authorization_freeze_record")
    op.drop_index("idx_authorization_freeze_agent", table_name="authorization_freeze_record")
    op.drop_index("idx_authorization_freeze_authorization", table_name="authorization_freeze_record")
    op.drop_table("authorization_freeze_record")
