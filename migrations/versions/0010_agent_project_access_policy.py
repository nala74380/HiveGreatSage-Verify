r"""
文件位置: migrations/versions/0010_agent_project_access_policy.py
文件名称: 0010_agent_project_access_policy.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    新增代理等级驱动的项目准入与授权申请系统。

新增表:
    - agent_level_policy
    - project_access_policy
    - agent_project_auth_request
    - agent_project_access_invite

增强表:
    - agent_project_auth 增加 source / request_id / granted_by_admin_id / granted_reason

默认策略:
    - Lv.1 新手代理: 默认授信 200，最高 300，不允许自动开通
    - Lv.2 标准代理: 默认授信 1000，最高 1500，可自动开通基础项目
    - Lv.3 核心代理: 默认授信 4000，最高 5000，可自动开通基础/中级项目
    - Lv.4 渠道代理: 默认授信 10000，最高 15000，可自动开通大部分非隐藏项目

项目开通:
    - 项目开通本身不扣点。
    - 代理给用户授权项目时才按项目定价扣点。
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_agent_project_access_policy"
down_revision = "0009_authorization_charge_refund"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_level_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("level", sa.SmallInteger(), nullable=False, unique=True, comment="代理等级 Lv.1 - Lv.4"),
        sa.Column("level_name", sa.String(length=64), nullable=False, comment="等级名称"),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("default_credit_limit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("max_credit_limit", sa.Numeric(14, 2), nullable=False, server_default="0"),

        sa.Column("max_users_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("can_create_sub_agents", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_sub_agents", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("can_auto_open_project", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_open_project_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_priority", sa.SmallInteger(), nullable=False, server_default="0"),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint("level BETWEEN 1 AND 4", name="chk_agent_level_policy_level_range"),
        sa.CheckConstraint("default_credit_limit >= 0", name="chk_agent_level_default_credit_non_negative"),
        sa.CheckConstraint("max_credit_limit >= default_credit_limit", name="chk_agent_level_max_credit_ge_default"),
    )

    op.create_table(
        "project_access_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("game_project.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "visibility_mode",
            sa.String(length=32),
            nullable=False,
            server_default="public",
            comment="public/level_limited/invite_only/hidden",
        ),
        sa.Column(
            "open_mode",
            sa.String(length=32),
            nullable=False,
            server_default="manual_review",
            comment="manual_review/auto_by_level/auto_by_condition/disabled",
        ),

        sa.Column("min_visible_agent_level", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("min_apply_agent_level", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("min_auto_open_agent_level", sa.SmallInteger(), nullable=True),

        sa.Column("min_available_points", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("allow_apply", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allow_auto_open", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("require_request_reason", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("cooldown_hours_after_reject", sa.Integer(), nullable=False, server_default="24"),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint(
            "visibility_mode IN ('public', 'level_limited', 'invite_only', 'hidden')",
            name="chk_project_access_visibility_mode",
        ),
        sa.CheckConstraint(
            "open_mode IN ('manual_review', 'auto_by_level', 'auto_by_condition', 'disabled')",
            name="chk_project_access_open_mode",
        ),
        sa.CheckConstraint("min_visible_agent_level BETWEEN 1 AND 4", name="chk_project_access_min_visible_level"),
        sa.CheckConstraint("min_apply_agent_level BETWEEN 1 AND 4", name="chk_project_access_min_apply_level"),
        sa.CheckConstraint(
            "min_auto_open_agent_level IS NULL OR min_auto_open_agent_level BETWEEN 1 AND 4",
            name="chk_project_access_min_auto_level",
        ),
        sa.CheckConstraint("min_available_points >= 0", name="chk_project_access_min_points_non_negative"),
    )

    op.create_index("idx_project_access_policy_project", "project_access_policy", ["project_id"])
    op.create_index("idx_project_access_policy_visibility", "project_access_policy", ["visibility_mode"])
    op.create_index("idx_project_access_policy_open_mode", "project_access_policy", ["open_mode"])

    op.create_table(
        "agent_project_auth_request",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False),

        sa.Column("request_reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
            comment="pending/approved/rejected/cancelled/auto_approved",
        ),

        sa.Column("reviewed_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("auto_approve_reason", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'auto_approved')",
            name="chk_agent_project_auth_request_status",
        ),
    )

    op.create_index(
        "idx_agent_project_auth_request_agent",
        "agent_project_auth_request",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_agent_project_auth_request_project",
        "agent_project_auth_request",
        ["project_id", "created_at"],
    )
    op.create_index(
        "idx_agent_project_auth_request_status",
        "agent_project_auth_request",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_agent_project_pending_request",
        "agent_project_auth_request",
        ["agent_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "agent_project_access_invite",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.UniqueConstraint("agent_id", "project_id", name="uq_agent_project_access_invite"),
    )

    op.create_index(
        "idx_agent_project_access_invite_agent",
        "agent_project_access_invite",
        ["agent_id", "project_id", "is_active"],
    )

    op.add_column(
        "agent_project_auth",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="admin_manual"),
    )
    op.add_column(
        "agent_project_auth",
        sa.Column("request_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "agent_project_auth",
        sa.Column("granted_by_admin_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_project_auth",
        sa.Column("granted_reason", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_agent_project_auth_request_id",
        "agent_project_auth",
        "agent_project_auth_request",
        ["request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_project_auth_granted_by_admin",
        "agent_project_auth",
        "admin",
        ["granted_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "chk_agent_project_auth_source",
        "agent_project_auth",
        "source IN ('admin_manual', 'request_approved', 'auto_approved')",
    )

    # 默认代理等级策略
    op.execute(
        """
        INSERT INTO agent_level_policy
            (level, level_name, description, default_credit_limit, max_credit_limit,
             max_users_default, can_create_sub_agents, max_sub_agents,
             can_auto_open_project, auto_open_project_limit, review_priority)
        VALUES
            (1, '新手代理', '初始代理，只能申请项目，不允许自动开通。', 200, 300, 0, false, 0, false, 0, 1),
            (2, '标准代理', '正常代理，可自动开通基础公开项目。', 1000, 1500, 0, false, 0, true, 10, 2),
            (3, '核心代理', '稳定代理，可自动开通基础与中级项目。', 4000, 5000, 0, false, 0, true, 30, 3),
            (4, '渠道代理', '渠道/总代，可开通更多非隐藏项目。', 10000, 15000, 0, true, 0, true, 100, 4)
        ON CONFLICT (level) DO NOTHING;
        """
    )

    # 给已有项目创建默认准入策略：公开可见 + 必须审核
    op.execute(
        """
        INSERT INTO project_access_policy
            (project_id, visibility_mode, open_mode,
             min_visible_agent_level, min_apply_agent_level, min_auto_open_agent_level,
             min_available_points, allow_apply, allow_auto_open, require_request_reason)
        SELECT
            id,
            'public',
            'manual_review',
            1,
            1,
            NULL,
            0,
            true,
            false,
            true
        FROM game_project
        ON CONFLICT (project_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_constraint("chk_agent_project_auth_source", "agent_project_auth", type_="check")
    op.drop_constraint("fk_agent_project_auth_granted_by_admin", "agent_project_auth", type_="foreignkey")
    op.drop_constraint("fk_agent_project_auth_request_id", "agent_project_auth", type_="foreignkey")

    op.drop_column("agent_project_auth", "granted_reason")
    op.drop_column("agent_project_auth", "granted_by_admin_id")
    op.drop_column("agent_project_auth", "request_id")
    op.drop_column("agent_project_auth", "source")

    op.drop_index("idx_agent_project_access_invite_agent", table_name="agent_project_access_invite")
    op.drop_table("agent_project_access_invite")

    op.drop_index("uq_agent_project_pending_request", table_name="agent_project_auth_request")
    op.drop_index("idx_agent_project_auth_request_status", table_name="agent_project_auth_request")
    op.drop_index("idx_agent_project_auth_request_project", table_name="agent_project_auth_request")
    op.drop_index("idx_agent_project_auth_request_agent", table_name="agent_project_auth_request")
    op.drop_table("agent_project_auth_request")

    op.drop_index("idx_project_access_policy_open_mode", table_name="project_access_policy")
    op.drop_index("idx_project_access_policy_visibility", table_name="project_access_policy")
    op.drop_index("idx_project_access_policy_project", table_name="project_access_policy")
    op.drop_table("project_access_policy")

    op.drop_table("agent_level_policy")