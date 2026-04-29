r"""
文件位置: migrations/versions/0011_agent_business_profile.py
文件名称: 0011_agent_business_profile.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    新增代理业务画像表 agent_business_profile。

设计目的:
    - 保留 agent.level 作为代理组织层级 / 代理树深度。
    - 新增 agent_business_profile.tier_level 作为代理业务等级 Lv.1 - Lv.4。
    - 避免“组织层级”和“代理等级”混用。

代理业务等级默认:
    Lv.1 新手代理
    Lv.2 标准代理
    Lv.3 核心代理
    Lv.4 渠道代理

注意:
    agent_level_policy 表已在 0010 中创建，本迁移不重复创建。
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_agent_business_profile"
down_revision = "0010_agent_project_access_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_business_profile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            comment="代理ID",
        ),
        sa.Column(
            "tier_level",
            sa.SmallInteger(),
            nullable=False,
            server_default="1",
            comment="代理业务等级 Lv.1 - Lv.4；不同于 agent.level 组织层级",
        ),
        sa.Column(
            "credit_limit_override",
            sa.Numeric(14, 2),
            nullable=True,
            comment="单代理授信额度覆盖值；为空时使用等级默认授信",
        ),
        sa.Column(
            "max_credit_limit_override",
            sa.Numeric(14, 2),
            nullable=True,
            comment="单代理最高授信覆盖值；为空时使用等级最高授信",
        ),
        sa.Column(
            "can_create_sub_agents_override",
            sa.Boolean(),
            nullable=True,
            comment="是否允许创建下级代理覆盖；为空时使用等级策略",
        ),
        sa.Column(
            "max_sub_agents_override",
            sa.Integer(),
            nullable=True,
            comment="最大下级代理数覆盖；为空时使用等级策略",
        ),
        sa.Column(
            "risk_status",
            sa.String(length=24),
            nullable=False,
            server_default="normal",
            comment="normal/watch/restricted/frozen",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="管理员备注"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint("tier_level BETWEEN 1 AND 4", name="chk_agent_business_tier_level"),
        sa.CheckConstraint(
            "risk_status IN ('normal', 'watch', 'restricted', 'frozen')",
            name="chk_agent_business_risk_status",
        ),
        sa.CheckConstraint(
            "credit_limit_override IS NULL OR credit_limit_override >= 0",
            name="chk_agent_business_credit_override_non_negative",
        ),
        sa.CheckConstraint(
            "max_credit_limit_override IS NULL OR max_credit_limit_override >= 0",
            name="chk_agent_business_max_credit_override_non_negative",
        ),
        sa.CheckConstraint(
            "max_sub_agents_override IS NULL OR max_sub_agents_override >= 0",
            name="chk_agent_business_max_sub_agents_override_non_negative",
        ),
    )

    op.create_index(
        "idx_agent_business_profile_tier",
        "agent_business_profile",
        ["tier_level"],
    )
    op.create_index(
        "idx_agent_business_profile_risk",
        "agent_business_profile",
        ["risk_status"],
    )

    # 给已有代理创建默认业务画像。
    op.execute(
        """
        INSERT INTO agent_business_profile
            (agent_id, tier_level, risk_status)
        SELECT
            id, 1, 'normal'
        FROM agent
        ON CONFLICT (agent_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_agent_business_profile_risk", table_name="agent_business_profile")
    op.drop_index("idx_agent_business_profile_tier", table_name="agent_business_profile")
    op.drop_table("agent_business_profile")