r"""
文件位置: app/models/main/agent_profile.py
文件名称: agent_profile.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-29
版本: V1.0.0
功能说明:
    代理业务画像 ORM 模型。

重要边界:
    - Agent.level 表示代理组织层级 / 代理树深度。
    - AgentBusinessProfile.tier_level 表示代理业务等级 Lv.1 - Lv.4。
"""

from datetime import datetime

from sqlalchemy import (
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentBusinessProfile(Base):
    __tablename__ = "agent_business_profile"
    __table_args__ = (
        CheckConstraint("tier_level BETWEEN 1 AND 4", name="chk_agent_business_tier_level"),
        CheckConstraint(
            "risk_status IN ('normal', 'watch', 'restricted', 'frozen')",
            name="chk_agent_business_risk_status",
        ),
        CheckConstraint(
            "credit_limit_override IS NULL OR credit_limit_override >= 0",
            name="chk_agent_business_credit_override_non_negative",
        ),
        CheckConstraint(
            "max_credit_limit_override IS NULL OR max_credit_limit_override >= 0",
            name="chk_agent_business_max_credit_override_non_negative",
        ),
        CheckConstraint(
            "max_sub_agents_override IS NULL OR max_sub_agents_override >= 0",
            name="chk_agent_business_max_sub_agents_override_non_negative",
        ),
        Index("idx_agent_business_profile_tier", "tier_level"),
        Index("idx_agent_business_profile_risk", "risk_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    tier_level: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="1",
        comment="代理业务等级 Lv.1 - Lv.4",
    )

    credit_limit_override: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="单代理授信额度覆盖值；为空时使用等级默认授信",
    )

    max_credit_limit_override: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="单代理最高授信覆盖值；为空时使用等级最高授信",
    )

    can_create_sub_agents_override: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="是否允许创建下级代理覆盖；为空时使用等级策略",
    )

    max_sub_agents_override: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最大下级代理数覆盖；为空时使用等级策略",
    )

    risk_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="normal",
        comment="normal/watch/restricted/frozen",
    )

    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )