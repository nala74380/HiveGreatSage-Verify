"""authorization batch core

Revision ID: 0026_authorization_batch_core
Revises: 0025_loginlog_device_id_cleanup
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_authorization_batch_core"
down_revision = "0025_identity_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_action",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("preview_snapshot", sa.JSON(), nullable=True),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("accounting_snapshot", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'committed', 'failed')", name="chk_authorization_action_status_enum"),
        sa.ForeignKeyConstraint(["authorization_id"], ["authorization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("authorization_id", "idempotency_key", name="uq_authorization_action_idempotency"),
    )
    op.create_index("idx_authorization_action_authorization", "authorization_action", ["authorization_id", "created_at"])
    op.create_index("idx_authorization_action_type", "authorization_action", ["action_type", "created_at"])
    op.create_index("idx_authorization_action_user", "authorization_action", ["user_id", "created_at"])

    op.create_table(
        "authorization_batch",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_project_id", sa.Integer(), nullable=False),
        sa.Column("user_level", sa.String(length=20), nullable=False),
        sa.Column("authorized_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bound_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("merged_into_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("created_action_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_action_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("authorized_devices >= 0", name="chk_authorization_batch_devices_non_negative"),
        sa.CheckConstraint("bound_devices >= 0", name="chk_authorization_batch_bound_devices_non_negative"),
        sa.CheckConstraint("status IN ('active', 'suspended', 'expired', 'merged', 'cancelled')", name="chk_authorization_batch_status_enum"),
        sa.CheckConstraint("user_level IN ('trial', 'normal', 'vip', 'svip', 'tester')", name="chk_authorization_batch_user_level_enum"),
        sa.ForeignKeyConstraint(["authorization_id"], ["authorization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_action_id"], ["authorization_action.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["game_project_id"], ["game_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merged_into_batch_id"], ["authorization_batch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_action_id"], ["authorization_action.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_authorization_batch_authorization_status", "authorization_batch", ["authorization_id", "status"])
    op.create_index("idx_authorization_batch_user_project", "authorization_batch", ["user_id", "game_project_id"])
    op.create_index("idx_authorization_batch_valid_until", "authorization_batch", ["valid_until"])

    op.create_table(
        "authorization_lot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.BigInteger(), nullable=True),
        sa.Column("lot_type", sa.String(length=32), nullable=False),
        sa.Column("user_level", sa.String(length=20), nullable=False),
        sa.Column("device_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_hours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("period_hours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_cost", sa.Numeric(18, 4), server_default="0", nullable=False),
        sa.Column("deducted_points", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("charged_consumed", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("credit_consumed", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("deducted_points >= 0", name="chk_authorization_lot_deducted_points_non_negative"),
        sa.CheckConstraint("device_count >= 0", name="chk_authorization_lot_device_count_non_negative"),
        sa.CheckConstraint("lot_type IN ('grant', 'add_devices', 'renew', 'topup_align', 'level_upgrade_diff')", name="chk_authorization_lot_type_enum"),
        sa.CheckConstraint("paid_hours >= 0", name="chk_authorization_lot_paid_hours_non_negative"),
        sa.CheckConstraint("period_hours >= 0", name="chk_authorization_lot_period_hours_non_negative"),
        sa.ForeignKeyConstraint(["action_id"], ["authorization_action.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorization_id"], ["authorization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["authorization_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_authorization_lot_action", "authorization_lot", ["action_id"])
    op.create_index("idx_authorization_lot_authorization", "authorization_lot", ["authorization_id"])
    op.create_index("idx_authorization_lot_batch", "authorization_lot", ["batch_id"])

    op.add_column("device_binding", sa.Column("batch_id", sa.BigInteger(), nullable=True, comment="设备归属授权批次"))

    op.execute(
        """
        INSERT INTO authorization_batch (
            authorization_id,
            user_id,
            game_project_id,
            user_level,
            authorized_devices,
            bound_devices,
            valid_from,
            valid_until,
            status,
            created_at,
            updated_at
        )
        SELECT
            a.id,
            a.user_id,
            a.game_project_id,
            a.user_level,
            a.authorized_devices,
            COALESCE(d.bound_devices, 0),
            COALESCE(a.valid_from, now()),
            a.valid_until,
            CASE
                WHEN a.status IN ('active', 'suspended', 'expired') THEN a.status
                ELSE 'active'
            END,
            now(),
            now()
        FROM "authorization" a
        LEFT JOIN (
            SELECT user_id, game_project_id, count(*) AS bound_devices
            FROM device_binding
            WHERE status = 'active'
            GROUP BY user_id, game_project_id
        ) d
          ON d.user_id = a.user_id
         AND d.game_project_id = a.game_project_id
        """
    )

    op.execute(
        """
        UPDATE device_binding db
           SET batch_id = b.id
          FROM authorization_batch b
         WHERE db.user_id = b.user_id
           AND db.game_project_id = b.game_project_id
           AND b.status IN ('active', 'suspended', 'expired')
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM device_binding WHERE batch_id IS NULL) THEN
                RAISE EXCEPTION 'device_binding contains rows without matching authorization batch';
            END IF;
        END $$;
        """
    )

    op.alter_column("device_binding", "batch_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_foreign_key(
        "fk_device_binding_batch_id_authorization_batch",
        "device_binding",
        "authorization_batch",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("idx_device_binding_batch", "device_binding", ["batch_id"])


def downgrade() -> None:
    op.drop_index("idx_device_binding_batch", table_name="device_binding")
    op.drop_constraint("fk_device_binding_batch_id_authorization_batch", "device_binding", type_="foreignkey")
    op.drop_column("device_binding", "batch_id")

    op.drop_index("idx_authorization_lot_batch", table_name="authorization_lot")
    op.drop_index("idx_authorization_lot_authorization", table_name="authorization_lot")
    op.drop_index("idx_authorization_lot_action", table_name="authorization_lot")
    op.drop_table("authorization_lot")

    op.drop_index("idx_authorization_batch_valid_until", table_name="authorization_batch")
    op.drop_index("idx_authorization_batch_user_project", table_name="authorization_batch")
    op.drop_index("idx_authorization_batch_authorization_status", table_name="authorization_batch")
    op.drop_table("authorization_batch")

    op.drop_index("idx_authorization_action_user", table_name="authorization_action")
    op.drop_index("idx_authorization_action_type", table_name="authorization_action")
    op.drop_index("idx_authorization_action_authorization", table_name="authorization_action")
    op.drop_table("authorization_action")
