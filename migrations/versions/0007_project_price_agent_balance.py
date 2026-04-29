"""add project price and agent balance tables

Revision ID: 0007_project_price_agent_balance
Revises: 0006_add_is_deleted_to_user
Create Date: 2026-04-29

项目定价表：每个项目按用户级别设置点数单价
代理余额表：充值点数 + 授信点数 + 冻结授信
流水记录表：所有点数变动的完整历史
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_project_price_agent_balance"
down_revision = "0006_add_is_deleted_to_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 项目定价表 ──────────────────────────────────────────────
    op.create_table(
        "project_price",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("game_project.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_level", sa.String(20), nullable=False,
                  comment="用户级别: trial/normal/vip/svip/tester"),
        sa.Column("points_per_device", sa.Numeric(10, 4), nullable=False,
                  comment="授权一台设备消耗的点数"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("project_id", "user_level", name="uq_project_level_price"),
    )
    op.create_index("idx_project_price_project", "project_price", ["project_id"])

    # ── 代理余额表 ──────────────────────────────────────────────
    op.create_table(
        "agent_balance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(),
                  sa.ForeignKey("agent.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("charged_points", sa.Numeric(14, 4), nullable=False,
                  server_default="0", comment="充值点数（线下充值，管理员录入）"),
        sa.Column("credit_points", sa.Numeric(14, 4), nullable=False,
                  server_default="0", comment="授信点数（管理员授信，可冻结）"),
        sa.Column("frozen_credit", sa.Numeric(14, 4), nullable=False,
                  server_default="0", comment="已冻结的授信点数（不可使用）"),
        sa.Column("total_consumed", sa.Numeric(14, 4), nullable=False,
                  server_default="0", comment="累计消耗点数（统计用）"),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ── 点数流水记录表 ──────────────────────────────────────────
    op.create_table(
        "balance_transaction",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(),
                  sa.ForeignKey("agent.id", ondelete="CASCADE"),
                  nullable=False),
        # 流水类型: recharge=充值 credit=授信 consume=消耗 freeze=冻结 unfreeze=解冻 adjust=调整
        sa.Column("tx_type", sa.String(20), nullable=False),
        # 余额类型: charged=充值点数 credit=授信点数
        sa.Column("balance_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False,
                  comment="变动金额（正=增加，负=减少）"),
        sa.Column("balance_before", sa.Numeric(14, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 4), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("operated_by_admin_id", sa.Integer(), nullable=True,
                  comment="操作管理员 ID（消耗时为 NULL）"),
        sa.Column("related_user_id", sa.Integer(), nullable=True,
                  comment="关联用户 ID（消耗类型时填写）"),
        sa.Column("related_project_id", sa.Integer(), nullable=True,
                  comment="关联项目 ID"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_balance_tx_agent", "balance_transaction", ["agent_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_balance_tx_agent", "balance_transaction")
    op.drop_table("balance_transaction")
    op.drop_table("agent_balance")
    op.drop_index("idx_project_price_project", "project_price")
    op.drop_table("project_price")
