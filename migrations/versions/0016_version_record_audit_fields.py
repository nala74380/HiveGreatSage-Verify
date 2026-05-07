r"""
文件位置: migrations/versions/0016_version_record_audit_fields.py
文件名称: 0016_version_record_audit_fields.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    为主库热更新版本记录 version_record 增加发布审计字段。

新增字段:
    - released_by_admin_id: 发布管理员 ID
    - original_filename: 上传原始文件名（已安全化，只保留文件名）
    - file_size: 上传文件大小，单位 byte
    - request_id: 请求追踪 ID，待 RequestIdMiddleware 落地后写入
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_version_record_audit_fields"
down_revision = "0015_system_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "version_record",
        sa.Column(
            "released_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin.id", ondelete="SET NULL"),
            nullable=True,
            comment="发布该热更新包的管理员 ID",
        ),
    )
    op.add_column(
        "version_record",
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=True,
            comment="上传原始文件名，仅保留安全文件名，不含路径",
        ),
    )
    op.add_column(
        "version_record",
        sa.Column(
            "file_size",
            sa.BigInteger(),
            nullable=True,
            comment="上传文件大小，单位 byte",
        ),
    )
    op.add_column(
        "version_record",
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=True,
            comment="发布请求 ID，待 RequestIdMiddleware 落地后写入",
        ),
    )
    op.create_index(
        "idx_version_record_released_by_admin",
        "version_record",
        ["released_by_admin_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_version_record_released_by_admin", table_name="version_record")
    op.drop_column("version_record", "request_id")
    op.drop_column("version_record", "file_size")
    op.drop_column("version_record", "original_filename")
    op.drop_column("version_record", "released_by_admin_id")
