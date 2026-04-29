r"""
文件位置: migrations/versions/0008_authorization_level_devices.py
文件名称: 0008_authorization_level_devices.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.1
功能说明:
    将用户等级、授权设备数从 User 全局维度迁移到 Authorization 项目授权维度。

迁移原因:
    旧模型:
        user.user_level
        user.max_devices
        user.expired_at

    无法表达:
        同一用户在 A 项目是普通，B 项目是 VIP；
        同一用户在 A 项目授权 20 台，B 项目授权 50 台；
        同一用户在不同项目有不同到期时间。

    新模型:
        authorization.user_level
        authorization.authorized_devices
        authorization.valid_until

安全口径:
    - 本迁移不会删除 user.user_level / user.max_devices / user.expired_at。
    - 旧字段暂时保留作兼容与回滚。
    - 新增字段会用旧 user 字段进行一次性回填。

改进历史:
    V1.0.1 - 修复 PostgreSQL 中 authorization 表名未加双引号导致的语法错误
    V1.0.0 - 初始迁移版本
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0008_authorization_level_devices"
down_revision = "0007_project_price_agent_balance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 新增字段，先给 server_default，便于旧数据平滑迁移
    op.add_column(
        "authorization",
        sa.Column(
            "user_level",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
            comment="该用户在此项目内的授权等级: trial/normal/vip/svip/tester",
        ),
    )

    op.add_column(
        "authorization",
        sa.Column(
            "authorized_devices",
            sa.Integer(),
            nullable=False,
            server_default="20",
            comment="该用户在此项目内授权的设备数量，0 表示无限制",
        ),
    )

    # 2. 添加约束
    op.create_check_constraint(
        "chk_authorization_user_level_enum",
        "authorization",
        "user_level IN ('trial', 'normal', 'vip', 'svip', 'tester')",
    )

    op.create_check_constraint(
        "chk_authorization_authorized_devices_non_negative",
        "authorization",
        "authorized_devices >= 0",
    )

    # 3. 回填旧数据
    #    注意：
    #      - authorization 是 PostgreSQL 敏感关键字语义词，必须加双引号。
    #      - user 也是敏感表名，也必须加双引号。
    #    回填规则：
    #      - authorization.user_level 从 user.user_level 回填
    #      - authorization.authorized_devices 从 user.max_devices 回填
    #      - authorization.valid_until 若自身为空，则从 user.expired_at 回填
    op.execute(
        """
        UPDATE "authorization" AS a
        SET
            user_level = COALESCE(u.user_level, 'normal'),
            authorized_devices = COALESCE(u.max_devices, 20),
            valid_until = COALESCE(a.valid_until, u.expired_at)
        FROM "user" AS u
        WHERE a.user_id = u.id
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "chk_authorization_authorized_devices_non_negative",
        "authorization",
        type_="check",
    )

    op.drop_constraint(
        "chk_authorization_user_level_enum",
        "authorization",
        type_="check",
    )

    op.drop_column("authorization", "authorized_devices")
    op.drop_column("authorization", "user_level")