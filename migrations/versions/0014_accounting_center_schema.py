r"""
文件位置: migrations/versions/0014_accounting_center_schema.py
文件名称: 0014_accounting_center_schema.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心数据库结构落地。

设计目标:
    以中后期账务中心为基准，建立正式账务域表结构。

新增表:
    - accounting_wallet
    - accounting_document
    - authorization_charge_snapshot
    - accounting_ledger_entry
    - accounting_reconciliation_run
    - accounting_reconciliation_item
    - accounting_adjustment_request
    - accounting_risk_event
    - agent_monthly_bill

说明:
    本迁移暂不删除旧表:
      - agent_balance
      - balance_transaction
      - authorization_charge

    原因:
      服务层尚未切换到 accounting_service.py。
      下一批会改服务层并切断旧写入路径。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_accounting_center_schema"
down_revision = "0013_remove_agent_user_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounting_wallet",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
        sa.Column("charged_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("frozen_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "available_credit",
            sa.Numeric(18, 2),
            sa.Computed("credit_balance - frozen_credit", persisted=True),
        ),
        sa.Column(
            "available_total",
            sa.Numeric(18, 2),
            sa.Computed("charged_balance + credit_balance - frozen_credit", persisted=True),
        ),
        sa.Column("total_recharged", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_credited", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_consumed", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_refunded", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_adjusted", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("last_recharge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_credit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_consume_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refund_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("risk_status", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("agent_id", name="uq_accounting_wallet_agent"),
        sa.CheckConstraint("charged_balance >= 0", name="ck_wallet_charged_balance_non_negative"),
        sa.CheckConstraint("credit_balance >= 0", name="ck_wallet_credit_balance_non_negative"),
        sa.CheckConstraint("frozen_credit >= 0", name="ck_wallet_frozen_credit_non_negative"),
        sa.CheckConstraint("frozen_credit <= credit_balance", name="ck_wallet_frozen_lte_credit"),
        sa.CheckConstraint("status IN ('active', 'locked', 'closed')", name="ck_wallet_status_enum"),
        sa.CheckConstraint(
            "risk_status IN ('normal', 'watch', 'restricted', 'frozen')",
            name="ck_wallet_risk_status_enum",
        ),
    )
    op.create_index("idx_accounting_wallet_agent", "accounting_wallet", ["agent_id"])
    op.create_index("idx_accounting_wallet_status", "accounting_wallet", ["status"])
    op.create_index("idx_accounting_wallet_risk_status", "accounting_wallet", ["risk_status"])

    op.create_table(
        "accounting_document",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_no", sa.String(64), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("authorization_id", sa.Integer(), sa.ForeignKey("authorization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="posted"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("document_no", name="uq_accounting_document_no"),
        sa.CheckConstraint(
            """
            document_type IN (
                'recharge',
                'credit',
                'freeze',
                'unfreeze',
                'authorization_charge',
                'delete_refund',
                'manual_adjust',
                'reconciliation_adjust',
                'reversal'
            )
            """,
            name="ck_accounting_document_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'posted', 'cancelled', 'reversed')",
            name="ck_accounting_document_status",
        ),
    )
    op.create_index("idx_accounting_document_agent", "accounting_document", ["agent_id", "created_at"])
    op.create_index("idx_accounting_document_type", "accounting_document", ["document_type", "created_at"])
    op.create_index("idx_accounting_document_project", "accounting_document", ["project_id", "created_at"])
    op.create_index("idx_accounting_document_user", "accounting_document", ["user_id", "created_at"])

    op.create_table(
        "authorization_charge_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("accounting_document.id", ondelete="SET NULL"), nullable=True),
        sa.Column("authorization_id", sa.Integer(), sa.ForeignKey("authorization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_level", sa.String(32), nullable=False),
        sa.Column("authorized_devices", sa.Integer(), nullable=False),
        sa.Column("billing_period", sa.String(32), nullable=False),
        sa.Column("billing_period_hours", sa.Integer(), nullable=False),
        sa.Column("period_count", sa.Integer(), nullable=False),
        sa.Column("paid_hours", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("original_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("charged_consumed", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit_consumed", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refund_status", sa.String(32), nullable=False, server_default="none"),
        sa.Column("refunded_points", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refunded_charged", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refunded_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("last_refund_paid_hours", sa.Integer(), nullable=True),
        sa.Column("last_refund_used_hours", sa.Integer(), nullable=True),
        sa.Column("last_refund_used_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("last_refund_points", sa.Numeric(18, 2), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("user_level IN ('trial', 'normal', 'vip', 'svip')", name="ck_charge_snapshot_user_level"),
        sa.CheckConstraint("authorized_devices > 0", name="ck_charge_snapshot_devices_positive"),
        sa.CheckConstraint("billing_period IN ('week', 'month')", name="ck_charge_snapshot_billing_period"),
        sa.CheckConstraint("billing_period_hours > 0", name="ck_charge_snapshot_period_hours_positive"),
        sa.CheckConstraint("period_count > 0", name="ck_charge_snapshot_period_count_positive"),
        sa.CheckConstraint("paid_hours > 0", name="ck_charge_snapshot_paid_hours_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_charge_snapshot_unit_price_non_negative"),
        sa.CheckConstraint("original_cost >= 0", name="ck_charge_snapshot_original_cost_non_negative"),
        sa.CheckConstraint("charged_consumed >= 0", name="ck_charge_snapshot_charged_consumed_non_negative"),
        sa.CheckConstraint("credit_consumed >= 0", name="ck_charge_snapshot_credit_consumed_non_negative"),
        sa.CheckConstraint("refunded_points >= 0", name="ck_charge_snapshot_refunded_points_non_negative"),
        sa.CheckConstraint("refunded_charged >= 0", name="ck_charge_snapshot_refunded_charged_non_negative"),
        sa.CheckConstraint("refunded_credit >= 0", name="ck_charge_snapshot_refunded_credit_non_negative"),
        sa.CheckConstraint(
            "refund_status IN ('none', 'partial', 'refunded', 'no_refund')",
            name="ck_charge_snapshot_refund_status",
        ),
    )
    op.create_index("idx_charge_snapshot_authorization", "authorization_charge_snapshot", ["authorization_id"])
    op.create_index("idx_charge_snapshot_agent", "authorization_charge_snapshot", ["agent_id", "created_at"])
    op.create_index("idx_charge_snapshot_user_project", "authorization_charge_snapshot", ["user_id", "project_id"])
    op.create_index("idx_charge_snapshot_refund_status", "authorization_charge_snapshot", ["refund_status"])

    op.create_table(
        "accounting_ledger_entry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_no", sa.String(64), nullable=False),
        sa.Column("wallet_id", sa.BigInteger(), sa.ForeignKey("accounting_wallet.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("balance_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("business_category", sa.String(64), nullable=False),
        sa.Column("business_subtype", sa.String(64), nullable=True),
        sa.Column("related_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_authorization_id", sa.Integer(), sa.ForeignKey("authorization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_charge_snapshot_id", sa.BigInteger(), sa.ForeignKey("authorization_charge_snapshot.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_document_id", sa.BigInteger(), sa.ForeignKey("accounting_document.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_text", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("status", sa.String(32), nullable=False, server_default="posted"),
        sa.Column("operated_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operated_by_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("entry_no", name="uq_accounting_ledger_entry_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_accounting_ledger_idempotency_key"),
        sa.CheckConstraint("direction IN ('in', 'out')", name="ck_ledger_direction"),
        sa.CheckConstraint(
            "entry_type IN ('recharge', 'credit', 'freeze', 'unfreeze', 'consume', 'refund', 'adjust', 'reversal')",
            name="ck_ledger_entry_type",
        ),
        sa.CheckConstraint("balance_type IN ('charged', 'credit')", name="ck_ledger_balance_type"),
        sa.CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        sa.CheckConstraint("status IN ('posted', 'reversed')", name="ck_ledger_status"),
        sa.CheckConstraint("source IN ('admin', 'agent', 'system')", name="ck_ledger_source"),
    )
    op.create_index("idx_ledger_agent_posted", "accounting_ledger_entry", ["agent_id", "posted_at"])
    op.create_index("idx_ledger_type_posted", "accounting_ledger_entry", ["entry_type", "posted_at"])
    op.create_index("idx_ledger_balance_type", "accounting_ledger_entry", ["balance_type", "posted_at"])
    op.create_index("idx_ledger_project", "accounting_ledger_entry", ["related_project_id", "posted_at"])
    op.create_index("idx_ledger_user", "accounting_ledger_entry", ["related_user_id", "posted_at"])
    op.create_index("idx_ledger_document", "accounting_ledger_entry", ["related_document_id"])
    op.create_index("idx_ledger_charge_snapshot", "accounting_ledger_entry", ["related_charge_snapshot_id"])

    op.create_table(
        "accounting_reconciliation_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_no", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("checked_wallets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("normal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("abnormal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("run_no", name="uq_accounting_reconciliation_run_no"),
        sa.CheckConstraint("scope_type IN ('all', 'agent')", name="ck_reconciliation_run_scope_type"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_reconciliation_run_status"),
    )
    op.create_index("idx_reconciliation_run_status", "accounting_reconciliation_run", ["status", "created_at"])

    op.create_table(
        "accounting_reconciliation_item",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("accounting_reconciliation_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("charged_balance_snapshot", sa.Numeric(18, 2), nullable=False),
        sa.Column("charged_balance_calculated", sa.Numeric(18, 2), nullable=False),
        sa.Column("charged_diff", sa.Numeric(18, 2), nullable=False),
        sa.Column("credit_balance_snapshot", sa.Numeric(18, 2), nullable=False),
        sa.Column("credit_balance_calculated", sa.Numeric(18, 2), nullable=False),
        sa.Column("credit_diff", sa.Numeric(18, 2), nullable=False),
        sa.Column("frozen_credit_snapshot", sa.Numeric(18, 2), nullable=False),
        sa.Column("frozen_credit_calculated", sa.Numeric(18, 2), nullable=False),
        sa.Column("frozen_diff", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("issue_detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('normal', 'abnormal', 'pending_review', 'fixed')",
            name="ck_reconciliation_item_status",
        ),
    )
    op.create_index("idx_reconciliation_item_run", "accounting_reconciliation_item", ["run_id"])
    op.create_index("idx_reconciliation_item_agent", "accounting_reconciliation_item", ["agent_id"])
    op.create_index("idx_reconciliation_item_status", "accounting_reconciliation_item", ["status"])

    op.create_table(
        "accounting_adjustment_request",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_no", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("balance_type", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_document_id", sa.BigInteger(), sa.ForeignKey("accounting_document.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("request_no", name="uq_accounting_adjustment_request_no"),
        sa.CheckConstraint("balance_type IN ('charged', 'credit')", name="ck_adjustment_balance_type"),
        sa.CheckConstraint("direction IN ('in', 'out')", name="ck_adjustment_direction"),
        sa.CheckConstraint("amount > 0", name="ck_adjustment_amount_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'posted', 'cancelled')",
            name="ck_adjustment_status",
        ),
    )
    op.create_index("idx_adjustment_agent", "accounting_adjustment_request", ["agent_id", "created_at"])
    op.create_index("idx_adjustment_status", "accounting_adjustment_request", ["status", "created_at"])

    op.create_table(
        "accounting_risk_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_no", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("risk_type", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolve_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_no", name="uq_accounting_risk_event_no"),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="ck_accounting_risk_level"),
        sa.CheckConstraint("status IN ('open', 'ignored', 'resolved')", name="ck_accounting_risk_status"),
    )
    op.create_index("idx_accounting_risk_agent", "accounting_risk_event", ["agent_id", "created_at"])
    op.create_index("idx_accounting_risk_project", "accounting_risk_event", ["project_id", "created_at"])
    op.create_index("idx_accounting_risk_type", "accounting_risk_event", ["risk_type", "created_at"])
    op.create_index("idx_accounting_risk_status", "accounting_risk_event", ["status", "created_at"])

    op.create_table(
        "agent_monthly_bill",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("bill_no", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bill_month", sa.String(7), nullable=False),
        sa.Column("opening_charged_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("opening_credit_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_recharge", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_freeze", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_unfreeze", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_consume", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_refund", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_adjust", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("closing_charged_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("closing_credit_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("bill_no", name="uq_agent_monthly_bill_no"),
        sa.UniqueConstraint("agent_id", "bill_month", name="uq_agent_monthly_bill_agent_month"),
        sa.CheckConstraint(
            "status IN ('draft', 'generated', 'confirmed', 'cancelled')",
            name="ck_agent_monthly_bill_status",
        ),
    )
    op.create_index("idx_agent_monthly_bill_agent", "agent_monthly_bill", ["agent_id", "bill_month"])
    op.create_index("idx_agent_monthly_bill_status", "agent_monthly_bill", ["status", "generated_at"])

    # 开发期迁移：把旧 agent_balance 快照复制到新 accounting_wallet。
    # 旧服务层尚未切换，旧表暂时保留。
    op.execute(
        """
        INSERT INTO accounting_wallet (
            agent_id,
            charged_balance,
            credit_balance,
            frozen_credit,
            total_consumed,
            updated_at
        )
        SELECT
            agent_id,
            charged_points,
            credit_points,
            frozen_credit,
            total_consumed,
            updated_at
        FROM agent_balance
        ON CONFLICT (agent_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_agent_monthly_bill_status", table_name="agent_monthly_bill")
    op.drop_index("idx_agent_monthly_bill_agent", table_name="agent_monthly_bill")
    op.drop_table("agent_monthly_bill")

    op.drop_index("idx_accounting_risk_status", table_name="accounting_risk_event")
    op.drop_index("idx_accounting_risk_type", table_name="accounting_risk_event")
    op.drop_index("idx_accounting_risk_project", table_name="accounting_risk_event")
    op.drop_index("idx_accounting_risk_agent", table_name="accounting_risk_event")
    op.drop_table("accounting_risk_event")

    op.drop_index("idx_adjustment_status", table_name="accounting_adjustment_request")
    op.drop_index("idx_adjustment_agent", table_name="accounting_adjustment_request")
    op.drop_table("accounting_adjustment_request")

    op.drop_index("idx_reconciliation_item_status", table_name="accounting_reconciliation_item")
    op.drop_index("idx_reconciliation_item_agent", table_name="accounting_reconciliation_item")
    op.drop_index("idx_reconciliation_item_run", table_name="accounting_reconciliation_item")
    op.drop_table("accounting_reconciliation_item")

    op.drop_index("idx_reconciliation_run_status", table_name="accounting_reconciliation_run")
    op.drop_table("accounting_reconciliation_run")

    op.drop_index("idx_ledger_charge_snapshot", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_document", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_user", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_project", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_balance_type", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_type_posted", table_name="accounting_ledger_entry")
    op.drop_index("idx_ledger_agent_posted", table_name="accounting_ledger_entry")
    op.drop_table("accounting_ledger_entry")

    op.drop_index("idx_charge_snapshot_refund_status", table_name="authorization_charge_snapshot")
    op.drop_index("idx_charge_snapshot_user_project", table_name="authorization_charge_snapshot")
    op.drop_index("idx_charge_snapshot_agent", table_name="authorization_charge_snapshot")
    op.drop_index("idx_charge_snapshot_authorization", table_name="authorization_charge_snapshot")
    op.drop_table("authorization_charge_snapshot")

    op.drop_index("idx_accounting_document_user", table_name="accounting_document")
    op.drop_index("idx_accounting_document_project", table_name="accounting_document")
    op.drop_index("idx_accounting_document_type", table_name="accounting_document")
    op.drop_index("idx_accounting_document_agent", table_name="accounting_document")
    op.drop_table("accounting_document")

    op.drop_index("idx_accounting_wallet_risk_status", table_name="accounting_wallet")
    op.drop_index("idx_accounting_wallet_status", table_name="accounting_wallet")
    op.drop_index("idx_accounting_wallet_agent", table_name="accounting_wallet")
    op.drop_table("accounting_wallet")