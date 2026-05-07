r"""
文件位置: migrations/versions/0017_audit_log.py
文件名称: 0017_audit_log.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    新增平台通用审计日志表 audit_log。

设计目标:
    - 支持管理员 / 代理 / 用户 / 系统关键操作审计。
    - 与 request_id 打通，支持跨接口排障。
    - 不记录敏感明文。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_audit_log"
down_revision = "0016_version_record_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_type", sa.String(32), nullable=False, comment="操作者类型：admin / agent / user / system"),
        sa.Column("actor_id", sa.Integer(), nullable=True, comment="操作者 ID，system 可为空"),
        sa.Column("action", sa.String(128), nullable=False, comment="动作名称，如 update.publish / user.create"),
        sa.Column("target_type", sa.String(64), nullable=True, comment="目标类型，如 version_record / user / agent"),
        sa.Column("target_id", sa.String(64), nullable=True, comment="目标 ID，统一存字符串，兼容 UUID / int"),
        sa.Column("summary", sa.Text(), nullable=True, comment="人工可读摘要，不应包含敏感信息"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="结构化元数据，不应包含敏感信息"),
        sa.Column("request_id", sa.String(64), nullable=True, comment="请求追踪 ID"),
        sa.Column("ip_address", sa.String(64), nullable=True, comment="客户端 IP，后续由可信代理策略统一写入"),
        sa.Column("user_agent", sa.Text(), nullable=True, comment="客户端 User-Agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_index("idx_audit_log_actor", "audit_log", ["actor_type", "actor_id", "created_at"])
    op.create_index("idx_audit_log_action", "audit_log", ["action", "created_at"])
    op.create_index("idx_audit_log_target", "audit_log", ["target_type", "target_id", "created_at"])
    op.create_index("idx_audit_log_request_id", "audit_log", ["request_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_request_id", table_name="audit_log")
    op.drop_index("idx_audit_log_target", table_name="audit_log")
    op.drop_index("idx_audit_log_action", table_name="audit_log")
    op.drop_index("idx_audit_log_actor", table_name="audit_log")
    op.drop_table("audit_log")
