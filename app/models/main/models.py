r"""
文件位置: app/models/main/models.py
文件名称: models.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    hive_platform 主库的全部 ORM 模型，与数据库设计.md v2 对齐：
      - Admin（管理员）
      - Agent（多级代理，自引用外键）
      - User（用户，5级）
      - Authorization（授权：用户×游戏项目）
      - DeviceBinding（设备绑定）
      - GameProject（游戏项目注册表）
      - LoginLog（登录日志，只写不删）
    字段类型与数据库设计文档严格对齐：
      - password_hash: VARCHAR(255)
      - user_level: VARCHAR(20)
      - login_log: ip_address INET / success BOOLEAN / fail_reason
      - game_project: 含 project_uuid
改进历史: 无
调试信息:
    关系加载策略统一使用 lazy="select"（默认），需要性能优化时再改 joinedload。
    Agent 自引用关系需注意 foreign_keys 参数指定，避免 SQLAlchemy 报 AmbiguousForeignKeys。
"""

import uuid
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
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── 管理员表 ──────────────────────────────────────────────────
class Admin(Base):
    __tablename__ = "admin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    agents_created: Mapped[list["Agent"]] = relationship(
        "Agent", back_populates="created_by_admin", foreign_keys="Agent.created_by_admin_id"
    )

    def __repr__(self) -> str:
        return f"<Admin id={self.id} username={self.username}>"


# ── 代理表（自引用，多级代理树）─────────────────────────────────
class Agent(Base):
    __tablename__ = "agent"
    __table_args__ = (
        # 创建者约束：顶级代理必须有 admin 创建者；子代理必须有父代理
        CheckConstraint(
            "(parent_agent_id IS NULL AND created_by_admin_id IS NOT NULL) "
            "OR (parent_agent_id IS NOT NULL)",
            name="chk_agent_creator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # 自引用外键：ON DELETE RESTRICT 禁止删除有子代理的代理
    parent_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    # 由管理员直接创建时记录（顶级代理）
    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin.id"), nullable=True
    )

    # max_users=0 表示无限制（D1 决策）
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    commission_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    parent: Mapped["Agent | None"] = relationship(
        "Agent",
        back_populates="children",
        foreign_keys=[parent_agent_id],
        remote_side="Agent.id",
    )
    children: Mapped[list["Agent"]] = relationship(
        "Agent",
        back_populates="parent",
        foreign_keys=[parent_agent_id],
    )
    created_by_admin: Mapped["Admin | None"] = relationship(
        "Admin",
        back_populates="agents_created",
        foreign_keys=[created_by_admin_id],
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="created_by_agent"
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} username={self.username} level={self.level}>"


# ── 用户表 ────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        # tester 级别只能由管理员创建
        CheckConstraint(
            "user_level != 'tester' OR created_by_admin = TRUE",
            name="chk_tester_creator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # 5 级用户体系（D1 决策）
    user_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        # CheckConstraint 在数据库层强制
    )

    created_by_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent.id"), nullable=True
    )
    created_by_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )  # active / suspended / expired
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 关系
    created_by_agent: Mapped["Agent | None"] = relationship(
        "Agent", back_populates="users"
    )
    authorizations: Mapped[list["Authorization"]] = relationship(
        "Authorization", back_populates="user", cascade="all, delete-orphan"
    )
    device_bindings: Mapped[list["DeviceBinding"]] = relationship(
        "DeviceBinding", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} level={self.user_level}>"


# ── 游戏项目注册表 ─────────────────────────────────────────────
class GameProject(Base):
    __tablename__ = "game_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # UUID 供客户端使用（不暴露内部自增 ID），登录时传 project_uuid
    project_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    code_name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 如 "game_001"，同时是数据库名后缀
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 对应 PostgreSQL 数据库名：hive_game_{code_name}
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    authorizations: Mapped[list["Authorization"]] = relationship(
        "Authorization", back_populates="game_project"
    )

    def __repr__(self) -> str:
        return f"<GameProject id={self.id} code_name={self.code_name}>"


# ── 授权表（用户 × 游戏项目）─────────────────────────────────
class Authorization(Base):
    __tablename__ = "authorization"
    __table_args__ = (
        UniqueConstraint("user_id", "game_project_id", name="uq_user_game"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    game_project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_project.id"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # NULL = 永久有效
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="authorizations")
    game_project: Mapped["GameProject"] = relationship(
        "GameProject", back_populates="authorizations"
    )

    def __repr__(self) -> str:
        return f"<Authorization user={self.user_id} game={self.game_project_id}>"


# ── 设备绑定表 ────────────────────────────────────────────────
class DeviceBinding(Base):
    __tablename__ = "device_binding"
    __table_args__ = (
        UniqueConstraint("user_id", "device_fingerprint", name="uq_user_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    device_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="device_bindings")

    def __repr__(self) -> str:
        return f"<DeviceBinding user={self.user_id} fp={self.device_fingerprint[:16]}...>"


# ── 登录日志（只写不删，用于审计）────────────────────────────
class LoginLog(Base):
    __tablename__ = "login_log"
    __table_args__ = (
        Index("idx_login_log_user", "user_id", "login_at"),
        Index("idx_login_log_ip", "ip_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=True
    )
    device_fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)  # PostgreSQL INET
    client_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 'pc'/'android'
    game_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fail_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # None=成功；'fail_auth'/'fail_device_limit'/'fail_expired' 等
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<LoginLog user={self.user_id} success={self.success} at={self.login_at}>"