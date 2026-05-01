r"""
文件位置: app/models/main/system_setting.py
文件名称: system_setting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    系统设置 ORM 模型。

设计边界:
    - system_setting 只存放平台运行期可变业务配置。
    - 不存放 SECRET_KEY / 数据库密码 / Redis 密码 / JWT 密钥等敏感部署配置。
    - 网络设置、客户端连接策略、热更新策略、安全策略等可以逐步纳入此表。

当前重点:
    - network category。
    - D 模式公网中转 / 隧道模式配置。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemSetting(Base):
    __tablename__ = "system_setting"
    __table_args__ = (
        UniqueConstraint("category", "setting_key", name="uq_system_setting_category_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="配置分类：network/display/security/update/log_audit/maintenance 等",
    )
    setting_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="配置键",
    )
    setting_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="配置值，按 value_type 解析",
    )
    value_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="string",
        comment="string/int/float/bool/json",
    )

    is_editable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        comment="是否允许后台编辑",
    )
    is_secret: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="是否敏感。敏感配置默认不明文展示。",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin.id", ondelete="SET NULL"),
        nullable=True,
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

    def __repr__(self) -> str:
        return f"<SystemSetting {self.category}.{self.setting_key}>"