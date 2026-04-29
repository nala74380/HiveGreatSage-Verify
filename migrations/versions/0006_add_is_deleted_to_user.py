"""add is_deleted to user

Revision ID: 0006_add_is_deleted_to_user
Revises: 0005_add_imsi_to_device_binding
Create Date: 2026-04-29

区分"已删除"（is_deleted=True）与"已停用"（status='suspended'）：
- 已停用：管理员手动停用，仍在列表中显示（有停用徽章），可随时恢复
- 已删除：通过删除操作软删除，默认不在列表中显示（过滤 is_deleted=True）
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_add_is_deleted_to_user"
down_revision = "0006_version_record_main"   # 接在 version_record 迁移之后，修复分岔问题
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="软删除标记，True=已删除（默认不显示）",
        ),
    )
    # 为常用查询加索引
    op.create_index("idx_user_is_deleted", "user", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("idx_user_is_deleted", table_name="user")
    op.drop_column("user", "is_deleted")
