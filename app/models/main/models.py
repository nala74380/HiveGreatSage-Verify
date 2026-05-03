r"""
文件位置: app/models/main/models.py
文件名称: models.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-29
版本: v2.0.0
功能说明:
    hive_platform 主库的全部 ORM 模型。

核心表:
      - Admin（管理员）
      - Agent（多级代理，自引用外键）
      - User（账号主体）
      - Authorization（用户 × 项目授权）
      - DeviceBinding（用户 × 项目 × 设备绑定）
      - GameProject（项目注册表）
      - AgentProjectAuth（代理 × 项目授权）
      - LoginLog（登录日志）
      - VersionRecord（主库热更新版本记录）
      - ProjectPrice（项目定价）

已删除的旧表（迁移至 app/models/main/accounting.py）:
      - AuthorizationCharge → AuthorizationChargeSnapshot
      - AgentBalance → AccountingWallet
      - BalanceTransaction → AccountingLedgerEntry

重要模型调整:
    v2.0.0 (2026-05-03):
      - 删除 AuthorizationCharge / AgentBalance / BalanceTransaction ORM 模型（D018）。
      - 账务模型迁移至 app/models/main/accounting.py。
      - DeviceBinding.game_project_id 改为 NOT NULL。
      - GameProject 和 Agent 移除对旧模型的 relationship。

    v1.0.7:
      - 移除旧账号数量限制口径。
      - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。

    v1.0.6:
      - DeviceBinding 新增 game_project_id。
      - 设备绑定口径调整为 user_id + game_project_id + device_fingerprint。

    v1.0.5:
      - 新增 AuthorizationCharge 授权扣点快照表（v2.0.0 已删除，改用 AuthorizationChargeSnapshot）。

    v1.0.4:
      - Authorization 新增 user_level / authorized_devices。
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

    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
        comment="管理员状态: active / suspended",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    agents_created: Mapped[list["Agent"]] = relationship(
        "Agent",
        back_populates="created_by_admin",
        foreign_keys="Agent.created_by_admin_id",
    )

    def __repr__(self) -> str:
        return f"<Admin id={self.id} username={self.username}>"


# ── 代理表 ────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agent"
    __table_args__ = (
        CheckConstraint(
            "(parent_agent_id IS NULL AND created_by_admin_id IS NOT NULL) "
            "OR (parent_agent_id IS NOT NULL)",
            name="chk_agent_creator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    parent_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agent.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 代理组织层级 / 代理树深度，不是业务等级。
    # 代理业务等级使用 AgentBusinessProfile.tier_level。
    level: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )

    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin.id"),
        nullable=True,
    )

    commission_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

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
        "User",
        back_populates="created_by_agent",
    )
    project_auths: Mapped[list["AgentProjectAuth"]] = relationship(
        "AgentProjectAuth",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    def __repr__(self) -> str:
        return f"<Agent id={self.id} username={self.username} level={self.level}>"


# ── 用户表 ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    created_by_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agent.id"),
        nullable=True,
    )
    created_by_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="软删除标记：True=已删除",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    created_by_agent: Mapped["Agent | None"] = relationship(
        "Agent",
        back_populates="users",
    )
    authorizations: Mapped[list["Authorization"]] = relationship(
        "Authorization",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    device_bindings: Mapped[list["DeviceBinding"]] = relationship(
        "DeviceBinding",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"


# ── 项目注册表 ─────────────────────────────────────────────────

class GameProject(Base):
    __tablename__ = "game_project"
    __table_args__ = (
        CheckConstraint(
            "project_type IN ('game', 'verification')",
            name="chk_project_type_enum",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
    )
    code_name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    project_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="game",
        comment="game=游戏项目 / verification=普通验证项目",
    )
    db_name: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    authorizations: Mapped[list["Authorization"]] = relationship(
        "Authorization",
        back_populates="game_project",
    )
    agent_project_auths: Mapped[list["AgentProjectAuth"]] = relationship(
        "AgentProjectAuth",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    version_records: Mapped[list["VersionRecord"]] = relationship(
        "VersionRecord",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    prices: Mapped[list["ProjectPrice"]] = relationship(
        "ProjectPrice",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    device_bindings: Mapped[list["DeviceBinding"]] = relationship(
        "DeviceBinding",
        back_populates="game_project",
    )

    def __repr__(self) -> str:
        return f"<GameProject id={self.id} code={self.code_name} type={self.project_type}>"


# ── 代理项目授权表 ─────────────────────────────────────────────

class AgentProjectAuth(Base):
    __tablename__ = "agent_project_auth"
    __table_args__ = (
        UniqueConstraint("agent_id", "project_id", name="uq_agent_project"),
        Index("idx_agent_project_auth_agent", "agent_id"),
        Index("idx_agent_project_auth_project", "project_id"),
        CheckConstraint(
            "source IN ('admin_manual', 'request_approved', 'auto_approved')",
            name="chk_agent_project_auth_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id", ondelete="CASCADE"),
        nullable=False,
    )

    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # 项目授权来源:
    # admin_manual      = 管理员手动开通
    # request_approved = 管理员批准代理申请
    # auto_approved    = 系统自动开通
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="admin_manual",
        comment="admin_manual/request_approved/auto_approved",
    )

    request_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_project_auth_request.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联代理项目开通申请 ID",
    )
    granted_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin.id", ondelete="SET NULL"),
        nullable=True,
        comment="批准开通该项目的管理员 ID",
    )
    granted_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="项目授权原因 / 审核备注 / 自动开通原因",
    )

    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="project_auths",
    )
    project: Mapped["GameProject"] = relationship(
        "GameProject",
        back_populates="agent_project_auths",
    )

    def __repr__(self) -> str:
        return (
            f"<AgentProjectAuth agent={self.agent_id} "
            f"project={self.project_id} source={self.source}>"
        )


# ── 授权表：用户 × 项目 ───────────────────────────────────────

class Authorization(Base):
    __tablename__ = "authorization"
    __table_args__ = (
        UniqueConstraint("user_id", "game_project_id", name="uq_user_game"),
        CheckConstraint(
            "user_level IN ('trial', 'normal', 'vip', 'svip', 'tester')",
            name="chk_authorization_user_level_enum",
        ),
        CheckConstraint(
            "authorized_devices >= 0",
            name="chk_authorization_authorized_devices_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id"),
        nullable=False,
    )

    user_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="normal",
        comment="该用户在此项目内的授权等级: trial/normal/vip/svip/tester",
    )
    authorized_devices: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="20",
        comment="该用户在此项目内授权的设备数，0 表示无限制",
    )

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="authorizations",
    )
    game_project: Mapped["GameProject"] = relationship(
        "GameProject",
        back_populates="authorizations",
    )

    def __repr__(self) -> str:
        return (
            f"<Authorization user={self.user_id} project={self.game_project_id} "
            f"level={self.user_level} devices={self.authorized_devices}>"
        )


# ── 设备绑定表 ────────────────────────────────────────────────

class DeviceBinding(Base):
    __tablename__ = "device_binding"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "game_project_id",
            "device_fingerprint",
            name="uq_user_project_device",
        ),
        Index("idx_device_binding_user_project", "user_id", "game_project_id"),
        Index("idx_device_binding_project_last_seen", "game_project_id", "last_seen_at"),
        Index("idx_device_binding_device", "device_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id", ondelete="CASCADE"),
        nullable=False,
        comment="绑定所属项目",
    )

    device_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)

    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    imsi: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="设备 IMSI 码，登录成功后单独上传",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="device_bindings",
    )
    game_project: Mapped["GameProject"] = relationship(
        "GameProject",
        back_populates="device_bindings",
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceBinding user={self.user_id} project={self.game_project_id} "
            f"fp={self.device_fingerprint[:16]}...>"
        )


# ── 版本记录表 ────────────────────────────────────────────────

class VersionRecord(Base):
    __tablename__ = "version_record"
    __table_args__ = (
        UniqueConstraint(
            "game_project_id",
            "client_type",
            "version",
            name="uq_project_client_version",
        ),
        Index(
            "idx_version_record_project_client",
            "game_project_id",
            "client_type",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    game_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_type: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    package_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    force_update: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    project: Mapped["GameProject"] = relationship(
        "GameProject",
        back_populates="version_records",
    )

    def __repr__(self) -> str:
        return f"<VersionRecord project={self.game_project_id} {self.client_type} v{self.version}>"


# ── 登录日志表 ────────────────────────────────────────────────

class LoginLog(Base):
    __tablename__ = "login_log"
    __table_args__ = (
        Index("idx_login_log_user", "user_id", "login_at"),
        Index("idx_login_log_ip", "ip_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user.id"),
        nullable=True,
    )
    device_fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    client_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    game_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fail_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<LoginLog user={self.user_id} success={self.success}>"


# ── 项目定价表 ────────────────────────────────────────────────

class ProjectPrice(Base):
    __tablename__ = "project_price"
    __table_args__ = (
        UniqueConstraint("project_id", "user_level", name="uq_project_level_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="用户级别: trial/normal/vip/svip/tester",
    )
    points_per_device: Mapped[float] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="授权一台设备消耗的点数",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped["GameProject"] = relationship(
        "GameProject",
        back_populates="prices",
    )

    def __repr__(self) -> str:
        return f"<ProjectPrice project={self.project_id} level={self.user_level} pts={self.points_per_device}>"


