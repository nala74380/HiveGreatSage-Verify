r"""
文件位置: app/models/game/models.py
文件名称: models.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    游戏项目库（hive_game_{code_name}）的全部 ORM 模型。
    每个游戏项目拥有独立数据库，本文件定义标准模板表结构。

    包含：
      - GameBase        : 游戏库专属 DeclarativeBase（与主库 Base 完全分离）
      - ProjectConfig   : 项目全局配置（KV 结构）
      - ScriptParamDef  : 脚本参数定义（元数据，PC 中控动态生成参数 UI）
      - UserScriptParam : 用户脚本参数值（按用户覆盖默认值）
      - DeviceRuntime   : 设备运行时数据（Redis 心跳批量落库的目标表）
      - VersionRecord   : 热更新版本记录（PC 包 / 安卓包分开管理）

    设计要点：
      1. GameBase 与主库 Base 完全独立，Alembic 的 target_metadata 只用主库
         Base.metadata，不包含 GameBase.metadata，确保不会误生成游戏表迁移。
      2. 游戏库建表统一通过 GameBase.metadata.create_all(bind=engine) 完成，
         调用方：scripts/init_data.py 和 /admin/api/projects/{id}/init-db 接口。
      3. user_id、device_id 等跨库引用字段不设数据库外键约束（跨库无法建外键），
         由应用层在写入前校验数据合法性。
      4. version_record 的活跃版本唯一约束通过部分索引实现：
         UNIQUE ON (client_type) WHERE is_active = TRUE
         确保每种客户端类型在任意时刻只有一个活跃版本。

关联文档:
    [[01-网络验证系统/数据库设计]] 第三节
    [[01-网络验证系统/Redis心跳落库策略]]

改进历史:
    V1.0.0 - 初始版本，对齐数据库设计.md v2 定稿

调试信息:
    已知问题: 无
    游戏库连接通过 app/database.py 的 _get_game_engine(code_name) 动态获取。
    建表命令（手动触发）: GameBase.metadata.create_all(bind=sync_engine)
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── 游戏库专属 Base（与主库 Base 完全分离）───────────────────
# 分离原因：Alembic 的 env.py 只注册主库 Base.metadata 作为迁移目标，
# 游戏表不经过 Alembic，避免在主库误建游戏表或生成无效迁移脚本。
class GameBase(DeclarativeBase):
    pass


# ── 项目配置表（KV 结构）─────────────────────────────────────
class ProjectConfig(GameBase):
    """
    游戏项目全局配置，采用 KV 结构存储。
    适合存储少量、不频繁变动的配置项，如服务器区服名称、活动开关等。
    """
    __tablename__ = "project_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    config_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ProjectConfig key={self.config_key}>"


# ── 脚本参数定义表（元数据）──────────────────────────────────
class ScriptParamDef(GameBase):
    """
    脚本参数定义（元数据层）。
    描述该游戏有哪些可配置参数、类型、默认值、选项等。
    PC 中控根据此表动态渲染参数配置 UI，无需硬编码参数列表。
    """
    __tablename__ = "script_param_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
        comment="参数键名，如 farm_map_id / auto_sell_threshold",
    )
    param_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="参数类型：int / float / string / bool / enum",
    )
    default_value: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON 格式的默认值，如 '1' / '\"北境\"' / 'true'",
    )
    options: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="enum 类型的可选项列表，如 [{\"value\": 1, \"label\": \"新手村\"}]",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="PC 中控上显示的参数名称",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="参数说明，显示在 PC 中控的 tooltip 中",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
        comment="PC 中控参数列表的显示排序（升序）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    user_params: Mapped[list["UserScriptParam"]] = relationship(
        "UserScriptParam",
        back_populates="param_def",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScriptParamDef key={self.param_key} type={self.param_type}>"


# ── 用户脚本参数值表 ──────────────────────────────────────────
class UserScriptParam(GameBase):
    """
    用户为该游戏设置的参数值（覆盖 ScriptParamDef 中的默认值）。
    安卓脚本启动时拉取此表，合并默认值后作为运行参数。

    user_id 为跨库引用（来自 hive_platform.user.id），不设数据库外键。
    应用层在写入前校验 user_id 合法性。
    """
    __tablename__ = "user_script_param"
    __table_args__ = (
        UniqueConstraint("user_id", "param_def_id", name="uq_user_param"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 跨库引用，无数据库外键约束
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    param_def_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("script_param_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    param_value: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="用户设置的值，JSON 格式",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 关系
    param_def: Mapped["ScriptParamDef"] = relationship(
        "ScriptParamDef", back_populates="user_params"
    )

    def __repr__(self) -> str:
        return f"<UserScriptParam user={self.user_id} param={self.param_def_id}>"


# ── 设备运行时数据表 ──────────────────────────────────────────
class DeviceRuntime(GameBase):
    """
    安卓脚本心跳上报数据的持久化存储（Celery 批量落库目标）。

    数据流：
      安卓脚本每 30 秒上报
        → FastAPI 写入 Redis（Key: device:runtime:{game_id}:{user_id}:{device_fp}）
        → Celery Beat 每 30 秒执行批量 UPSERT 到本表
        → PC 中控优先读 Redis，Redis 无数据时回落本表

    device_id 对应 hive_platform.device_binding.device_fingerprint（无外键，跨库）。
    user_id   对应 hive_platform.user.id（无外键，跨库）。

    game_data 使用 JSONB，各游戏自定义字段，如：
      {"map": "北境", "gold": 1024, "task": "日常采集", "error_count": 0}
    """
    __tablename__ = "device_runtime"
    __table_args__ = (
        Index("idx_device_runtime_user", "user_id"),
        Index("idx_device_runtime_last_seen", "last_seen"),
    )

    # 以设备指纹作为主键，天然唯一，适合 ON CONFLICT DO UPDATE 的 UPSERT 模式
    device_id: Mapped[str] = mapped_column(
        String(128), primary_key=True,
        comment="设备唯一标识，对应 device_binding.device_fingerprint",
    )
    # 跨库引用，无数据库外键约束
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="来自 hive_platform.user.id，跨库无外键",
    )
    status: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="运行状态：running / idle / error / offline",
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="最后一次心跳时间，用于判断设备是否在线",
    )
    game_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="游戏自定义数据，各游戏字段不同，格式由游戏适配层定义",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DeviceRuntime device={self.device_id[:16]}... user={self.user_id}>"


# 注意：热更新版本记录表 VersionRecord 已迁移到主库 app/models/main/models.py。
# 游戏库中不再包含此表。客户端和管理端统一从主库读写。
# 迁移决策：D014 (2026-04-26)
