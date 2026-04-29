r"""
文件位置: migrations/versions/0009_authorization_charge_refund.py
文件名称: 0009_authorization_charge_refund.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    新增授权扣点快照表 authorization_charge，并为 balance_transaction 增加 related_charge_id。

设计原因:
    删除用户需要按剩余未使用时间返还点数。
    退款不能直接读取当前 ProjectPrice，否则项目改价后会产生错账。
    因此授权扣点时必须保存当时的价格、周期、设备数、原始扣点、扣点来源等快照。

退款规则:
    - 试用 trial: 按周计费，1 周 = 168 小时。
    - 普通 / VIP / SVIP: 按月计费，1 月 = 720 小时。
    - 删除用户时，不足 1 小时按 1 小时计算。
    - 返点 = 原始扣点 - 每小时成本 × 已使用小时数 - 已返还点数。
    - 每小时成本 = 原始扣点 / 已购买总小时数。
    - 已过期授权不返点。
    - 管理员免费授权不返点。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_authorization_charge_refund"
down_revision = "0008_authorization_level_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorization_charge",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),

        sa.Column(
            "authorization_id",
            sa.Integer(),
            sa.ForeignKey("authorization.id", ondelete="CASCADE"),
            nullable=False,
            comment="对应的用户项目授权 ID",
        ),
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agent.id", ondelete="RESTRICT"),
            nullable=False,
            comment="产生扣点的代理 ID",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
            comment="被授权用户 ID",
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("game_project.id", ondelete="RESTRICT"),
            nullable=False,
            comment="授权项目 ID",
        ),

        sa.Column("user_level", sa.String(length=20), nullable=False, comment="授权时用户等级快照"),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=False, comment="授权时单价快照"),
        sa.Column("authorized_devices", sa.Integer(), nullable=False, comment="授权设备数快照"),

        sa.Column("billing_period", sa.String(length=20), nullable=False, comment="week/month"),
        sa.Column("billing_period_hours", sa.Integer(), nullable=False, comment="单个计费周期小时数"),
        sa.Column("period_count", sa.Integer(), nullable=False, comment="购买周期数"),
        sa.Column("paid_hours", sa.Integer(), nullable=False, comment="已购买总小时数"),

        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, comment="授权开始时间快照"),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False, comment="授权到期时间快照"),

        sa.Column("original_cost", sa.Numeric(14, 4), nullable=False, comment="原始总扣点"),
        sa.Column("charged_consumed", sa.Numeric(14, 4), nullable=False, server_default="0", comment="从充值点数扣除的部分"),
        sa.Column("credit_consumed", sa.Numeric(14, 4), nullable=False, server_default="0", comment="从授信点数扣除的部分"),

        sa.Column("refunded_points", sa.Numeric(14, 4), nullable=False, server_default="0", comment="累计已返点"),
        sa.Column("refund_status", sa.String(length=20), nullable=False, server_default="none", comment="none/refunded/no_refund"),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True, comment="最后返点时间"),

        sa.Column("last_refund_paid_hours", sa.Integer(), nullable=True, comment="最后一次返点时的购买总小时数"),
        sa.Column("last_refund_used_hours", sa.Integer(), nullable=True, comment="最后一次返点时的已使用小时数"),
        sa.Column("last_refund_used_cost", sa.Numeric(14, 4), nullable=True, comment="最后一次返点时的已使用点数"),
        sa.Column("last_refund_points", sa.Numeric(14, 4), nullable=True, comment="最后一次返点金额"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint(
            "user_level IN ('trial', 'normal', 'vip', 'svip')",
            name="chk_authorization_charge_user_level_enum",
        ),
        sa.CheckConstraint(
            "authorized_devices > 0",
            name="chk_authorization_charge_devices_positive",
        ),
        sa.CheckConstraint(
            "billing_period_hours > 0",
            name="chk_authorization_charge_period_hours_positive",
        ),
        sa.CheckConstraint(
            "period_count > 0",
            name="chk_authorization_charge_period_count_positive",
        ),
        sa.CheckConstraint(
            "paid_hours > 0",
            name="chk_authorization_charge_paid_hours_positive",
        ),
        sa.CheckConstraint(
            "original_cost >= 0",
            name="chk_authorization_charge_original_cost_non_negative",
        ),
        sa.CheckConstraint(
            "charged_consumed >= 0",
            name="chk_authorization_charge_charged_consumed_non_negative",
        ),
        sa.CheckConstraint(
            "credit_consumed >= 0",
            name="chk_authorization_charge_credit_consumed_non_negative",
        ),
        sa.CheckConstraint(
            "refunded_points >= 0",
            name="chk_authorization_charge_refunded_non_negative",
        ),
        sa.CheckConstraint(
            "refund_status IN ('none', 'refunded', 'no_refund')",
            name="chk_authorization_charge_refund_status_enum",
        ),
    )

    op.create_index(
        "idx_authorization_charge_authorization",
        "authorization_charge",
        ["authorization_id"],
    )
    op.create_index(
        "idx_authorization_charge_agent",
        "authorization_charge",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_authorization_charge_user_project",
        "authorization_charge",
        ["user_id", "project_id"],
    )
    op.create_index(
        "idx_authorization_charge_refund_status",
        "authorization_charge",
        ["refund_status"],
    )

    op.add_column(
        "balance_transaction",
        sa.Column(
            "related_charge_id",
            sa.BigInteger(),
            nullable=True,
            comment="关联授权扣点快照 ID，用于扣点/返点审计",
        ),
    )

    op.create_index(
        "idx_balance_tx_related_charge",
        "balance_transaction",
        ["related_charge_id"],
    )

    op.create_foreign_key(
        "fk_balance_transaction_related_charge",
        "balance_transaction",
        "authorization_charge",
        ["related_charge_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_balance_transaction_related_charge",
        "balance_transaction",
        type_="foreignkey",
    )
    op.drop_index("idx_balance_tx_related_charge", table_name="balance_transaction")
    op.drop_column("balance_transaction", "related_charge_id")

    op.drop_index("idx_authorization_charge_refund_status", table_name="authorization_charge")
    op.drop_index("idx_authorization_charge_user_project", table_name="authorization_charge")
    op.drop_index("idx_authorization_charge_agent", table_name="authorization_charge")
    op.drop_index("idx_authorization_charge_authorization", table_name="authorization_charge")

    op.drop_table("authorization_charge")