r"""
文件位置: app/models/main/models.py
文件名称: models.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.3
功能说明:
    hive_platform 主库的全部 ORM 模型，与数据库设计.md v2 对齐：
      - Admin（管理员）
      - Agent（多级代理，自引用外键）
      - User（用户，5级）
      - Authorization（授权：用户×项目）
      - DeviceBinding（设备绑定）
      - GameProject（项目注册表，含 project_type）
      - AgentProjectAuth（代理×项目授权）
      - LoginLog（登录日志，只写不删）
    字段类型与数据库设计文档严格对齐：
      - password_hash: VARCHAR(255)
      - user_level: VARCHAR(20)
      - login_log: ip_address INET / success BOOLEAN / fail_reason
      - game_project: 含 project_uuid + project_type
改进历史:
    v1.0.3 (2026-04-25) - GameProject 加 project_type 字段，db_name 改为可空；
                          新增 AgentProjectAuth 模型；Agent 加 project_auths 关系
    v1.0.2 (2026-04-24) - User 表加 max_devices 字段
    v1.0.1 - User 表 __table_args__ 补入 chk_user_level_enum CHECK 约束
    v1.0.0 - 初始版本
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
        String(16), nullable=False, server_default="active",
        comment="用户状态: active / suspended"
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
        CheckConstraint(
            "(parent_agent_id IS NULL AND created_by_admin_id IS NOT NULL) "
            "OR (parent_agent_id IS NOT NULL)",
            name="chk_agent_creator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    parent_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent.id", ondelete="RESTRICT"), nullable=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin.id"), nullable=True
    )

    max_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    commission_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
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
        "Agent", back_populates="children",
        foreign_keys=[parent_agent_id], remote_side="Agent.id",
    )
    children: Mapped[list["Agent"]] = relationship(
        "Agent", back_populates="parent", foreign_keys=[parent_agent_id],
    )
    created_by_admin: Mapped["Admin | None"] = relationship(
        "Admin", back_populates="agents_created", foreign_keys=[created_by_admin_id],
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="created_by_agent")
    project_auths: Mapped[list["AgentProjectAuth"]] = relationship(
        "AgentProjectAuth", back_populates="agent", cascade="all, delete-orphan"
    )
    balance: Mapped["AgentBalance | None"] = relationship(
        "AgentBalance", back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} username={self.username} level={self.level}>"


# ── 用户表 ────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "user_level IN ('trial', 'normal', 'vip', 'svip', 'tester')",
            name="chk_user_level_enum",
        ),
        CheckConstraint(
            "user_level != 'tester' OR created_by_admin = TRUE",
            name="chk_tester_creator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    user_level: Mapped[str] = mapped_column(String(20), nullable=False)

    created_by_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent.id"), nullable=True
    )
    created_by_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
        comment="软删除标记：True=已删除（默认不显示）"
    )
    # 设备绑定上限（独立设置，不再由级别自动决定）
    max_devices: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="500"
    )
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
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    code_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 项目类型：game=游戏项目（需独立库）/ verification=普通验证项目
    project_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="game"
    )
    # 游戏项目才需要，验证项目为 NULL
    db_name: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    authorizations: Mapped[list["Authorization"]] = relationship(
        "Authorization", back_populates="game_project"
    )
    agent_project_auths: Mapped[list["AgentProjectAuth"]] = relationship(
        "AgentProjectAuth", back_populates="project", cascade="all, delete-orphan"
    )
    version_records: Mapped[list["VersionRecord"]] = relationship(
        "VersionRecord", back_populates="project", cascade="all, delete-orphan"
    )
    prices: Mapped[list["ProjectPrice"]] = relationship(
        "ProjectPrice", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GameProject id={self.id} code={self.code_name} type={self.project_type}>"


# ── 代理项目授权表（代理 × 项目）────────────────────────────────
class AgentProjectAuth(Base):
    """控制代理可操作（销售/管理）哪些项目。"""
    __tablename__ = "agent_project_auth"
    __table_args__ = (
        UniqueConstraint("agent_id", "project_id", name="uq_agent_project"),
        Index("idx_agent_project_auth_agent", "agent_id"),
        Index("idx_agent_project_auth_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    agent: Mapped["Agent"] = relationship("Agent", back_populates="project_auths")
    project: Mapped["GameProject"] = relationship(
        "GameProject", back_populates="agent_project_auths"
    )

    def __repr__(self) -> str:
        return f"<AgentProjectAuth agent={self.agent_id} project={self.project_id}>"


# ── 授权表（用户 × 项目）─────────────────────────────────────
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
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="authorizations")
    game_project: Mapped["GameProject"] = relationship(
        "GameProject", back_populates="authorizations"
    )

    def __repr__(self) -> str:
        return f"<Authorization user={self.user_id} project={self.game_project_id}>"


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
    imsi: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="设备 IMSI 码，登录成功后单独上传（接入契约 §8）"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )

    user: Mapped["User"] = relationship("User", back_populates="device_bindings")

    def __repr__(self) -> str:
        return f"<DeviceBinding user={self.user_id} fp={self.device_fingerprint[:16]}...>"


# ── 版本记录表（主库，支持游戏项目和验证项目）───────────────────
class VersionRecord(Base):
    """热更新版本记录，存储在主库，支持游戏项目和验证项目。"""
    __tablename__ = "version_record"
    __table_args__ = (
        UniqueConstraint(
            "game_project_id", "client_type", "version",
            name="uq_project_client_version",
        ),
        Index("idx_version_record_project_client",
              "game_project_id", "client_type", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False
    )
    client_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'pc' | 'android'
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    package_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    force_update: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped["GameProject"] = relationship("GameProject", back_populates="version_records")

    def __repr__(self) -> str:
        return f"<VersionRecord project={self.game_project_id} {self.client_type} v{self.version}>"


# ── 登录日志（只写不删）──────────────────────────────────────
class LoginLog(Base):
    __tablename__ = "login_log"
    __table_args__ = (
        Index("idx_login_log_user", "user_id", "login_at"),
        Index("idx_login_log_ip", "ip_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    client_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    game_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fail_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<LoginLog user={self.user_id} success={self.success}>"


# ── 项目定价表 ──────────────────────────────────────
class ProjectPrice(Base):
    """
    项目价格表。每个项目按用户级别设置授权一台设备消耗的点数。
    """
    __tablename__ = "project_price"
    __table_args__ = (
        UniqueConstraint("project_id", "user_level", name="uq_project_level_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_project.id", ondelete="CASCADE"), nullable=False
    )
    user_level: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="用户级别: trial/normal/vip/svip/tester"
    )
    points_per_device: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False,
        comment="授权一台设备消耗的点数"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["GameProject"] = relationship(
        "GameProject", back_populates="prices"
    )

    def __repr__(self) -> str:
        return f"<ProjectPrice project={self.project_id} level={self.user_level} pts={self.points_per_device}>"


# ── 代理余额表 ──────────────────────────────────────
class AgentBalance(Base):
    """
    代理余额表（每个代理唯一一条）。
    charged_points：线下充値，管理员录入，优先使用。
    credit_points：管理员授信的点数，可被冻结。
    frozen_credit：已冻结的授信点数（不可使用）。
    实际可用 = charged_points + (credit_points - frozen_credit)
    """
    __tablename__ = "agent_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    charged_points: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0",
        comment="充値点数"
    )
    credit_points: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0",
        comment="授信点数"
    )
    frozen_credit: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0",
        comment="已冻结的授信点数"
    )
    total_consumed: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0",
        comment="累计消耗点数"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agent: Mapped["Agent"] = relationship(
        "Agent", back_populates="balance"
    )

    @property
    def available_points(self) -> float:
        """实际可用点数：充値 + (授信 - 冻结)"""
        return float(self.charged_points) + float(self.credit_points) - float(self.frozen_credit)

    def __repr__(self) -> str:
        return f"<AgentBalance agent={self.agent_id} available={self.available_points:.4f}>"


# ── 点数流水记录表 ────────────────────────────────────
class BalanceTransaction(Base):
    """
    点数流水完整历史。所有余额变动必须在此表记录。
    tx_type: recharge（充値）/ credit（授信）/ consume（消耗）/ freeze（冻结）/ unfreeze（解冻）/ adjust（修正）
    balance_type: charged（充値点数）/ credit（授信点数）
    """
    __tablename__ = "balance_transaction"
    __table_args__ = (
        Index("idx_balance_tx_agent", "agent_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    tx_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="recharge/credit/consume/freeze/unfreeze/adjust"
    )
    balance_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="charged=充値点数 credit=授信点数"
    )
    amount: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False,
        comment="变动金额（正=增加，负=减少）"
    )
    balance_before: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    operated_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<BalanceTx agent={self.agent_id} type={self.tx_type} amount={self.amount}>"
