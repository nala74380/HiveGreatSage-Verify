r"""
文件位置: migrations/versions/0013_remove_agent_user_quota.py
文件名称: 0013_remove_agent_user_quota.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    删除代理用户配额旧口径字段。

设计原因:
    Verify 当前业务口径已经迁移为：
      - 用户 User 是账号主体。
      - 用户是否能使用某项目，由 Authorization 项目授权决定。
      - 代理商业约束由项目准入、项目授权、授权设备数、授权周期和点数余额决定。

    因此，agent.max_users 与 agent_level_policy.max_users_default 会形成旧口径：
      “代理最多创建多少用户”。

    该旧口径会和新口径冲突：
      “创建用户不计费，给用户开通项目授权才扣点”。

变更内容:
    1. 删除 agent.max_users。
    2. 删除 agent_level_policy.max_users_default。

注意:
    - 本迁移是破坏性清理，不再保留用户配额硬约束。
    - 用户数量后续只作为统计字段 users_count / users_total 展示。
    - 代理能否继续扩展业务，应由点数余额、项目准入、项目授权、风险状态控制。
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_remove_agent_user_quota"
down_revision = "0012_device_binding_project_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agent", "max_users")
    op.drop_column("agent_level_policy", "max_users_default")


def downgrade() -> None:
    op.add_column(
        "agent_level_policy",
        sa.Column(
            "max_users_default",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已废弃：代理等级默认用户配额，仅用于回退旧版本",
        ),
    )
    op.add_column(
        "agent",
        sa.Column(
            "max_users",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已废弃：代理可创建用户数量上限，仅用于回退旧版本",
        ),
    )