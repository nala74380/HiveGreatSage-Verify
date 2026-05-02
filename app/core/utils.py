"""
文件位置: app/core/utils.py
名称: 共享工具函数
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-03
版本: V1.0.0
功能说明:
    全项目共享的工具函数，消除各 service 文件中的重复实现。

    包含:
      - 时间处理: now_utc, ensure_aware
      - 金额处理: money, money_float
      - 业务编号: make_business_no
      - 密码生成: generate_password
      - 共享查询: get_project_or_404, get_game_project_by_code, get_agent_scope_ids

改进历史:
    V1.0.0 (2026-05-03): 从各 service 文件中提取重复实现并统一
"""

import secrets
import string
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.main.models import Agent, GameProject


# ═══════════════════════════════════════════════════════════════
# 时间
# ═══════════════════════════════════════════════════════════════

def now_utc() -> datetime:
    """当前 UTC aware datetime。"""
    return datetime.now(tz=timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """统一 datetime 时区：naive → 视为 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ═══════════════════════════════════════════════════════════════
# 金额
# ═══════════════════════════════════════════════════════════════

def money(value: Any) -> Decimal:
    """统一金额为 Decimal，四舍五入到 0.01。"""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_float(value: Any) -> float:
    """Decimal → float。"""
    return float(money(value))


# ═══════════════════════════════════════════════════════════════
# 业务编号
# ═══════════════════════════════════════════════════════════════

def make_business_no(prefix: str) -> str:
    """生成业务编号：{prefix}-{timestamp}-{random}。"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{ts}-{uuid.uuid4().hex[:8].upper()}"


# ═══════════════════════════════════════════════════════════════
# 密码生成
# ═══════════════════════════════════════════════════════════════

def generate_password(length: int = 12) -> str:
    """生成随机密码（字母+数字）。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ═══════════════════════════════════════════════════════════════
# 共享查询
# ═══════════════════════════════════════════════════════════════

async def get_project_or_404(
    db: AsyncSession,
    project_id: int,
) -> GameProject:
    """按 ID 查找激活项目，不存在则 404。"""
    project = await db.get(GameProject, project_id)
    if not project or not project.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID={project_id} 不存在或已下线",
        )
    return project


async def get_game_project_by_code(
    db: AsyncSession,
    code_name: str,
) -> GameProject:
    """按 code_name 查找激活项目，不存在则 404。"""
    result = await db.execute(
        select(GameProject).where(
            GameProject.code_name == code_name,
            GameProject.is_active == True,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"游戏项目 '{code_name}' 不存在或已下线",
        )
    return project


async def get_agent_scope_ids(
    db: AsyncSession,
    agent_id: int,
) -> list[int]:
    """
    WITH RECURSIVE 获取代理权限范围内所有代理 ID（含自身）。

    典型用途：代理查看下级用户/设备时，先取得所有子代理 ID，
    再用 WHERE created_by_agent_id IN (...) 过滤。
    """
    sql = text("""
        WITH RECURSIVE scope AS (
            SELECT id FROM agent WHERE id = :agent_id
            UNION ALL
            SELECT a.id FROM agent a
            INNER JOIN scope s ON a.parent_agent_id = s.id
        )
        SELECT id FROM scope
    """)
    result = await db.execute(sql, {"agent_id": agent_id})
    return [row[0] for row in result.all()]
