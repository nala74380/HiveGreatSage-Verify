r"""
文件位置: app/models/main/accounting.py
文件名称: accounting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    账务中心 ORM 模型。

设计定位:
    账务中心是 Verify 系统中负责平台内部点数资产治理的统一业务域。

    它负责:
      - 代理钱包
      - 点数账本
      - 充值
      - 授信
      - 冻结 / 解冻
      - 授权扣点
      - 删除用户返点
      - 手动调账
      - 对账检查
      - 代理账单
      - 账务风险审计

    它不负责:
      - 微信 / 支付宝 / 银行真实收款
      - 发票
      - 合同
      - 代理提现
      - 游戏内收益
      - 真实人民币资金流水

核心原则:
    1. Wallet 是当前余额快照。
    2. Ledger 是不可变账本事实。
    3. Document 是一次业务事件 / 单据。
    4. 授权扣点必须保存价格快照。
    5. 出错不能改旧账，只能新增 adjust / reversal 记录。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccountingWallet(Base):
    """代理钱包快照表。"""

    __tablename__ = "accounting_wallet"
    __table_args__ = (
        CheckConstraint("charged_balance >= 0", name="ck_wallet_charged_balance_non_negative"),
        CheckConstraint("credit_balance >= 0", name="ck_wallet_credit_balance_non_negative"),
        CheckConstraint("frozen_credit >= 0", name="ck_wallet_frozen_credit_non_negative"),
        CheckConstraint("frozen_credit <= credit_balance", name="ck_wallet_frozen_lte_credit"),
        CheckConstraint("status IN ('active', 'locked', 'closed')", name="ck_wallet_status_enum"),
        CheckConstraint("risk_status IN ('normal', 'watch', 'restricted', 'frozen')", name="ck_wallet_risk_status_enum"),
        Index("idx_accounting_wallet_agent", "agent_id"),
        Index("idx_accounting_wallet_status", "status"),
        Index("idx_accounting_wallet_risk_status", "risk_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    agent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="代理 ID；一个代理只有一个钱包",
    )

    charged_balance: Mapped[float] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default="0",
        comment="充值点数余额",
    )
    credit_balance: Mapped[float] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default="0",
        comment="授信点数余额",
    )
    frozen_credit: Mapped[float] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default="0",
        comment="已冻结授信点数",
    )

    available_credit: Mapped[float] = mapped_column(
        Numeric(18, 2),
        Computed("credit_balance - frozen_credit", persisted=True),
        comment="可用授信点数",
    )
    available_total: Mapped[float] = mapped_column(
        Numeric(18, 2),
        Computed("charged_balance + credit_balance - frozen_credit", persisted=True),
        comment="可用总点数",
    )

    total_recharged: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_credited: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_consumed: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_refunded: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_adjusted: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    last_recharge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_credit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_consume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refund_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    risk_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="normal")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", foreign_keys=[agent_id])


class AccountingDocument(Base):
    """账务单据表。一次业务事件可以生成多条账本记录。"""

    __tablename__ = "accounting_document"
    __table_args__ = (
        UniqueConstraint("document_no", name="uq_accounting_document_no"),
        CheckConstraint(
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
        CheckConstraint("status IN ('draft', 'posted', 'cancelled', 'reversed')", name="ck_accounting_document_status"),
        Index("idx_accounting_document_agent", "agent_id", "created_at"),
        Index("idx_accounting_document_type", "document_type", "created_at"),
        Index("idx_accounting_document_project", "project_id", "created_at"),
        Index("idx_accounting_document_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    document_no: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)

    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True)
    authorization_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("authorization.id", ondelete="SET NULL"), nullable=True)

    total_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="posted")

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True)
    created_by_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", foreign_keys=[agent_id])
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("GameProject", foreign_keys=[project_id])
    authorization = relationship("Authorization", foreign_keys=[authorization_id])


class AuthorizationChargeSnapshot(Base):
    """授权扣点快照表。用于追溯授权扣点、删除用户返点和对账。"""

    __tablename__ = "authorization_charge_snapshot"
    __table_args__ = (
        CheckConstraint("user_level IN ('trial', 'normal', 'vip', 'svip')", name="ck_charge_snapshot_user_level"),
        CheckConstraint("authorized_devices > 0", name="ck_charge_snapshot_devices_positive"),
        CheckConstraint("billing_period IN ('week', 'month')", name="ck_charge_snapshot_billing_period"),
        CheckConstraint("billing_period_hours > 0", name="ck_charge_snapshot_period_hours_positive"),
        CheckConstraint("period_count > 0", name="ck_charge_snapshot_period_count_positive"),
        CheckConstraint("paid_hours > 0", name="ck_charge_snapshot_paid_hours_positive"),
        CheckConstraint("unit_price >= 0", name="ck_charge_snapshot_unit_price_non_negative"),
        CheckConstraint("original_cost >= 0", name="ck_charge_snapshot_original_cost_non_negative"),
        CheckConstraint("charged_consumed >= 0", name="ck_charge_snapshot_charged_consumed_non_negative"),
        CheckConstraint("credit_consumed >= 0", name="ck_charge_snapshot_credit_consumed_non_negative"),
        CheckConstraint("refunded_points >= 0", name="ck_charge_snapshot_refunded_points_non_negative"),
        CheckConstraint("refunded_charged >= 0", name="ck_charge_snapshot_refunded_charged_non_negative"),
        CheckConstraint("refunded_credit >= 0", name="ck_charge_snapshot_refunded_credit_non_negative"),
        CheckConstraint("refund_status IN ('none', 'partial', 'refunded', 'no_refund')", name="ck_charge_snapshot_refund_status"),
        Index("idx_charge_snapshot_authorization", "authorization_id"),
        Index("idx_charge_snapshot_agent", "agent_id", "created_at"),
        Index("idx_charge_snapshot_user_project", "user_id", "project_id"),
        Index("idx_charge_snapshot_refund_status", "refund_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    document_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accounting_document.id", ondelete="SET NULL"),
        nullable=True,
    )
    authorization_id: Mapped[int] = mapped_column(Integer, ForeignKey("authorization.id", ondelete="CASCADE"), nullable=False)

    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="RESTRICT"), nullable=False)

    user_level: Mapped[str] = mapped_column(String(32), nullable=False)
    authorized_devices: Mapped[int] = mapped_column(Integer, nullable=False)

    billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_period_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    period_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    original_cost: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    charged_consumed: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    credit_consumed: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    refund_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="none")
    refunded_points: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    refunded_charged: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    refunded_credit: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    last_refund_paid_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_refund_used_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_refund_used_cost: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    last_refund_points: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship("AccountingDocument", foreign_keys=[document_id])
    authorization = relationship("Authorization", foreign_keys=[authorization_id])
    agent = relationship("Agent", foreign_keys=[agent_id])
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("GameProject", foreign_keys=[project_id])


class AccountingLedgerEntry(Base):
    """不可变账本明细表。"""

    __tablename__ = "accounting_ledger_entry"
    __table_args__ = (
        UniqueConstraint("entry_no", name="uq_accounting_ledger_entry_no"),
        UniqueConstraint("idempotency_key", name="uq_accounting_ledger_idempotency_key"),
        CheckConstraint("direction IN ('in', 'out')", name="ck_ledger_direction"),
        CheckConstraint("entry_type IN ('recharge', 'credit', 'freeze', 'unfreeze', 'consume', 'refund', 'adjust', 'reversal')", name="ck_ledger_entry_type"),
        CheckConstraint("balance_type IN ('charged', 'credit')", name="ck_ledger_balance_type"),
        CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        CheckConstraint("status IN ('posted', 'reversed')", name="ck_ledger_status"),
        CheckConstraint("source IN ('admin', 'agent', 'system')", name="ck_ledger_source"),
        Index("idx_ledger_agent_posted", "agent_id", "posted_at"),
        Index("idx_ledger_type_posted", "entry_type", "posted_at"),
        Index("idx_ledger_balance_type", "balance_type", "posted_at"),
        Index("idx_ledger_project", "related_project_id", "posted_at"),
        Index("idx_ledger_user", "related_user_id", "posted_at"),
        Index("idx_ledger_document", "related_document_id"),
        Index("idx_ledger_charge_snapshot", "related_charge_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    entry_no: Mapped[str] = mapped_column(String(64), nullable=False)

    wallet_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("accounting_wallet.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    balance_type: Mapped[str] = mapped_column(String(32), nullable=False)

    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    business_category: Mapped[str] = mapped_column(String(64), nullable=False)
    business_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)

    related_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    related_project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True)
    related_authorization_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("authorization.id", ondelete="SET NULL"), nullable=True)
    related_charge_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("authorization_charge_snapshot.id", ondelete="SET NULL"), nullable=True)
    related_document_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("accounting_document.id", ondelete="SET NULL"), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="admin")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="posted")

    operated_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True)
    operated_by_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True)

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet = relationship("AccountingWallet", foreign_keys=[wallet_id])
    agent = relationship("Agent", foreign_keys=[agent_id])
    related_user = relationship("User", foreign_keys=[related_user_id])
    related_project = relationship("GameProject", foreign_keys=[related_project_id])
    related_authorization = relationship("Authorization", foreign_keys=[related_authorization_id])
    related_charge_snapshot = relationship("AuthorizationChargeSnapshot", foreign_keys=[related_charge_snapshot_id])
    related_document = relationship("AccountingDocument", foreign_keys=[related_document_id])
    operated_by_admin = relationship("Admin", foreign_keys=[operated_by_admin_id])
    operated_by_agent = relationship("Agent", foreign_keys=[operated_by_agent_id])


class AccountingReconciliationRun(Base):
    """账务对账批次。"""

    __tablename__ = "accounting_reconciliation_run"
    __table_args__ = (
        UniqueConstraint("run_no", name="uq_accounting_reconciliation_run_no"),
        CheckConstraint("scope_type IN ('all', 'agent')", name="ck_reconciliation_run_scope_type"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_reconciliation_run_status"),
        Index("idx_reconciliation_run_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    run_no: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")

    checked_wallets: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    normal_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    abnormal_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scope_agent = relationship("Agent", foreign_keys=[scope_agent_id])
    created_by_admin = relationship("Admin", foreign_keys=[created_by_admin_id])


class AccountingReconciliationItem(Base):
    """账务对账明细。"""

    __tablename__ = "accounting_reconciliation_item"
    __table_args__ = (
        CheckConstraint("status IN ('normal', 'abnormal', 'pending_review', 'fixed')", name="ck_reconciliation_item_status"),
        Index("idx_reconciliation_item_run", "run_id"),
        Index("idx_reconciliation_item_agent", "agent_id"),
        Index("idx_reconciliation_item_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounting_reconciliation_run.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)

    charged_balance_snapshot: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    charged_balance_calculated: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    charged_diff: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    credit_balance_snapshot: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    credit_balance_calculated: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    credit_diff: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    frozen_credit_snapshot: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    frozen_credit_calculated: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    frozen_diff: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("AccountingReconciliationRun", foreign_keys=[run_id])
    agent = relationship("Agent", foreign_keys=[agent_id])


class AccountingAdjustmentRequest(Base):
    """调账申请表。"""

    __tablename__ = "accounting_adjustment_request"
    __table_args__ = (
        UniqueConstraint("request_no", name="uq_accounting_adjustment_request_no"),
        CheckConstraint("balance_type IN ('charged', 'credit')", name="ck_adjustment_balance_type"),
        CheckConstraint("direction IN ('in', 'out')", name="ck_adjustment_direction"),
        CheckConstraint("amount > 0", name="ck_adjustment_amount_positive"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'posted', 'cancelled')", name="ck_adjustment_status"),
        Index("idx_adjustment_agent", "agent_id", "created_at"),
        Index("idx_adjustment_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    request_no: Mapped[str] = mapped_column(String(64), nullable=False)

    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)
    balance_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")

    created_by_admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("admin.id", ondelete="RESTRICT"), nullable=False)
    approved_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_document_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("accounting_document.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", foreign_keys=[agent_id])
    created_by_admin = relationship("Admin", foreign_keys=[created_by_admin_id])
    approved_by_admin = relationship("Admin", foreign_keys=[approved_by_admin_id])
    posted_document = relationship("AccountingDocument", foreign_keys=[posted_document_id])


class AccountingRiskEvent(Base):
    """账务风险事件。"""

    __tablename__ = "accounting_risk_event"
    __table_args__ = (
        UniqueConstraint("event_no", name="uq_accounting_risk_event_no"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="ck_accounting_risk_level"),
        CheckConstraint("status IN ('open', 'ignored', 'resolved')", name="ck_accounting_risk_status"),
        Index("idx_accounting_risk_agent", "agent_id", "created_at"),
        Index("idx_accounting_risk_project", "project_id", "created_at"),
        Index("idx_accounting_risk_type", "risk_type", "created_at"),
        Index("idx_accounting_risk_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    event_no: Mapped[str] = mapped_column(String(64), nullable=False)

    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    risk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True)
    resolve_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent = relationship("Agent", foreign_keys=[agent_id])
    project = relationship("GameProject", foreign_keys=[project_id])
    user = relationship("User", foreign_keys=[user_id])
    resolved_by_admin = relationship("Admin", foreign_keys=[resolved_by_admin_id])


class AgentMonthlyBill(Base):
    """代理月账单。"""

    __tablename__ = "agent_monthly_bill"
    __table_args__ = (
        UniqueConstraint("bill_no", name="uq_agent_monthly_bill_no"),
        UniqueConstraint("agent_id", "bill_month", name="uq_agent_monthly_bill_agent_month"),
        CheckConstraint("status IN ('draft', 'generated', 'confirmed', 'cancelled')", name="ck_agent_monthly_bill_status"),
        Index("idx_agent_monthly_bill_agent", "agent_id", "bill_month"),
        Index("idx_agent_monthly_bill_status", "status", "generated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    bill_no: Mapped[str] = mapped_column(String(64), nullable=False)

    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=False)
    bill_month: Mapped[str] = mapped_column(String(7), nullable=False, comment="YYYY-MM")

    opening_charged_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    opening_credit_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    total_recharge: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_credit: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_freeze: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_unfreeze: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_consume: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_refund: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total_adjust: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    closing_charged_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    closing_credit_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent = relationship("Agent", foreign_keys=[agent_id])