r"""
文件位置: app/models/main/project_access.py
文件名称: project_access.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    代理等级驱动的项目准入与授权申请 ORM 模型。

说明:
    该文件使用同一个 Base。
    与 app/models/main/models.py 中的主模型分离，避免主模型文件继续膨胀。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentLevelPolicy(Base):
    __tablename__ = "agent_level_policy"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="chk_agent_level_policy_level_range"),
        CheckConstraint("default_credit_limit >= 0", name="chk_agent_level_default_credit_non_negative"),
        CheckConstraint("max_credit_limit >= default_credit_limit", name="chk_agent_level_max_credit_ge_default"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    level_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    default_credit_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    max_credit_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")

    max_users_default: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    can_create_sub_agents: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    max_sub_agents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    can_auto_open_project: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    auto_open_project_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectAccessPolicy(Base):
    __tablename__ = "project_access_policy"
    __table_args__ = (
        CheckConstraint(
            "visibility_mode IN ('public', 'level_limited', 'invite_only', 'hidden')",
            name="chk_project_access_visibility_mode",
        ),
        CheckConstraint(
            "open_mode IN ('manual_review', 'auto_by_level', 'auto_by_condition', 'disabled')",
            name="chk_project_access_open_mode",
        ),
        CheckConstraint("min_visible_agent_level BETWEEN 1 AND 4", name="chk_project_access_min_visible_level"),
        CheckConstraint("min_apply_agent_level BETWEEN 1 AND 4", name="chk_project_access_min_apply_level"),
        CheckConstraint(
            "min_auto_open_agent_level IS NULL OR min_auto_open_agent_level BETWEEN 1 AND 4",
            name="chk_project_access_min_auto_level",
        ),
        CheckConstraint("min_available_points >= 0", name="chk_project_access_min_points_non_negative"),
        Index("idx_project_access_policy_project", "project_id"),
        Index("idx_project_access_policy_visibility", "visibility_mode"),
        Index("idx_project_access_policy_open_mode", "open_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    visibility_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="public")
    open_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual_review")

    min_visible_agent_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    min_apply_agent_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    min_auto_open_agent_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    min_available_points: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    allow_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    allow_auto_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    require_request_reason: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    cooldown_hours_after_reject: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentProjectAuthRequest(Base):
    __tablename__ = "agent_project_auth_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'auto_approved')",
            name="chk_agent_project_auth_request_status",
        ),
        Index("idx_agent_project_auth_request_agent", "agent_id", "created_at"),
        Index("idx_agent_project_auth_request_project", "project_id", "created_at"),
        Index("idx_agent_project_auth_request_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False)

    request_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")

    reviewed_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    auto_approve_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentProjectAccessInvite(Base):
    __tablename__ = "agent_project_access_invite"
    __table_args__ = (
        UniqueConstraint("agent_id", "project_id", name="uq_agent_project_access_invite"),
        Index("idx_agent_project_access_invite_agent", "agent_id", "project_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False)
    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admin.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())