r"""
文件位置: migrations/versions/0018_merge_user_legacy_audit_heads.py
文件名称: 0018_merge_user_legacy_audit_heads.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    合并 Alembic 迁移分叉。

背景:
    0015_system_setting 后出现两个 head:
      - 0016_user_legacy_fields
      - 0017_audit_log

    其中:
      - 0016_user_legacy_fields 用于清理 User 旧授权字段。
      - 0016_version_record_audit_fields -> 0017_audit_log 用于热更新发布审计字段和 audit_log。

说明:
    本迁移不修改任何表结构，只负责把两个 head 合并为单一 head，
    使 `alembic upgrade head` 恢复为确定路径。
"""

from alembic import op


revision = "0018_merge_user_legacy_audit_heads"
down_revision = ("0016_user_legacy_fields", "0017_audit_log")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge-only migration: no schema changes.
    pass


def downgrade() -> None:
    # Merge-only migration: no schema changes.
    pass
