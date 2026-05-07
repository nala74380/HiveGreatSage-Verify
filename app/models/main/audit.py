r"""
文件位置: app/models/main/audit.py
文件名称: audit.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    主库审计日志 ORM 模型。

设计目标:
    - 记录管理员 / 代理 / 用户关键操作。
    - 与 request_id 打通，用于跨接口排障。
    - 不记录敏感明文，如密码、Token、密钥、上传文件内容。

当前边界:
    - 只定义通用审计表 AuditLog。
    - 具体业务接入由 app/services/audit_service.py 提供统一函数。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """平台通用审计日志。"""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_actor", "actor_type", "actor_id", "created_at"),
        Index("idx_audit_log_action", "action", "created_at"),
        Index("idx_audit_log_target", "target_type", "target_id", "created_at"),
        Index("idx_audit_log_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    actor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="操作者类型：admin / agent / user / system",
    )
    actor_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="操作者 ID，system 可为空",
    )

    action: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="动作名称，如 update.publish / user.create",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="目标类型，如 version_record / user / agent",
    )
    target_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="目标 ID，统一存字符串，兼容 UUID / int",
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="人工可读摘要，不应包含敏感信息",
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="结构化元数据，不应包含敏感信息",
    )

    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="请求追踪 ID",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="客户端 IP，后续由可信代理策略统一写入",
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="客户端 User-Agent",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} actor={self.actor_type}:{self.actor_id} action={self.action}>"
