r"""
文件位置: migrations/versions/0012_device_binding_project_id.py
文件名称: 0012_device_binding_project_id.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    为 device_binding 增加 game_project_id，将设备绑定主口径从
    user_id + device_fingerprint 调整为 user_id + game_project_id + device_fingerprint。

设计原因:
    Verify 已经将用户授权迁移到 Authorization（用户 × 项目）维度。
    授权设备数由 Authorization.authorized_devices 表达，因此设备绑定也必须归属到项目维度。

迁移策略:
    1. 增加 device_binding.game_project_id，迁移期允许 NULL。
    2. 新增 game_project 外键。
    3. 删除旧唯一约束 uq_user_device。
    4. 新增唯一约束 uq_user_project_device。
    5. 增加项目维度查询索引。

注意:
    - 本迁移不会自动回填旧绑定的 game_project_id。
    - 开发单项目环境可手工回填：
      UPDATE device_binding SET game_project_id = 1 WHERE game_project_id IS NULL;
    - 生产或多项目环境不能盲目统一回填，应按 LoginLog 或人工审计拆分。
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_device_binding_project_id"
down_revision = "0011_agent_business_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_binding",
        sa.Column(
            "game_project_id",
            sa.Integer(),
            nullable=True,
            comment="绑定所属项目；迁移期允许为空，新登录绑定必须写入",
        ),
    )

    op.create_foreign_key(
        "fk_device_binding_game_project",
        "device_binding",
        "game_project",
        ["game_project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "uq_user_device",
        "device_binding",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_user_project_device",
        "device_binding",
        ["user_id", "game_project_id", "device_fingerprint"],
    )

    op.create_index(
        "idx_device_binding_user_project",
        "device_binding",
        ["user_id", "game_project_id"],
    )
    op.create_index(
        "idx_device_binding_project_last_seen",
        "device_binding",
        ["game_project_id", "last_seen_at"],
    )
    op.create_index(
        "idx_device_binding_device",
        "device_binding",
        ["device_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("idx_device_binding_device", table_name="device_binding")
    op.drop_index("idx_device_binding_project_last_seen", table_name="device_binding")
    op.drop_index("idx_device_binding_user_project", table_name="device_binding")

    op.drop_constraint(
        "uq_user_project_device",
        "device_binding",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_user_device",
        "device_binding",
        ["user_id", "device_fingerprint"],
    )

    op.drop_constraint(
        "fk_device_binding_game_project",
        "device_binding",
        type_="foreignkey",
    )
    op.drop_column("device_binding", "game_project_id")
