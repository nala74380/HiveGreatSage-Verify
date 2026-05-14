r"""
文件位置: app/routers/audit_admin.py
文件名称: audit_admin.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-07
版本: V1.0.0
功能说明:
    管理员端审计日志查询接口。

接口前缀:
    /admin/api/audit-logs

设计目标:
    - 让 audit_log 可按 request_id / actor / action / target 检索。
    - 支持分页与时间范围过滤。
    - 只读接口，不写审计日志，避免查询审计日志本身产生大量噪音。

安全边界:
    - 仅 Admin Token 可访问。
    - 不返回密码、Token 等敏感明文；写入端 audit_service 已做敏感字段脱敏。
    - metadata_json 原样返回已落库的结构化审计元数据，后续如需更严格展示策略可增加字段级白名单。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_main_db
from app.models.main.audit import AuditLog
from app.models.main.models import Admin

router = APIRouter()


def _audit_log_to_dict(log: AuditLog) -> dict[str, Any]:
    """将 AuditLog ORM 转为 API 输出字典。"""
    return {
        "id": log.id,
        "actor_type": log.actor_type,
        "actor_id": log.actor_id,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "summary": log.summary,
        "metadata": log.metadata_json,
        "request_id": log.request_id,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/", summary="审计日志列表")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    actor_type: str | None = Query(default=None, description="admin / agent / user / system"),
    actor_id: int | None = Query(default=None),
    action: str | None = Query(default=None, description="精确匹配动作名，如 user.create"),
    action_prefix: str | None = Query(default=None, description="动作名前缀，如 auth. / accounting."),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None, description="按用户 ID 聚合查询用户、授权、设备、账务相关审计"),
    request_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None, description="开始时间，ISO8601"),
    date_to: datetime | None = Query(default=None, description="结束时间，ISO8601"),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """
    查询审计日志。

    常用排障方式:
        - request_id 精确定位一次请求链路。
        - action_prefix=auth. 查看登录相关审计。
        - actor_type/actor_id 查看某个操作者历史动作。
        - target_type/target_id 查看某个对象的变更历史。
    """
    conditions = []

    if actor_type:
        conditions.append(AuditLog.actor_type == actor_type)
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)
    if action:
        conditions.append(AuditLog.action == action)
    if action_prefix:
        conditions.append(AuditLog.action.startswith(action_prefix))
    if target_type:
        conditions.append(AuditLog.target_type == target_type)
    if target_id:
        conditions.append(AuditLog.target_id == target_id)
    if user_id is not None:
        conditions.append(or_(
            (AuditLog.target_type == "user") & (AuditLog.target_id == str(user_id)),
            AuditLog.metadata_json["user_id"].astext == str(user_id),
        ))
    if request_id:
        conditions.append(AuditLog.request_id == request_id)
    if date_from:
        conditions.append(AuditLog.created_at >= date_from)
    if date_to:
        conditions.append(AuditLog.created_at <= date_to)

    base_q = select(AuditLog)
    if conditions:
        base_q = base_q.where(*conditions)

    total = (
        await db.execute(select(func.count()).select_from(base_q.subquery()))
    ).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        base_q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "logs": [_audit_log_to_dict(log) for log in logs],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "filters": {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "action_prefix": action_prefix,
            "target_type": target_type,
            "target_id": target_id,
            "user_id": user_id,
            "request_id": request_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    }


@router.get("/{audit_log_id}", summary="审计日志详情")
async def get_audit_log_detail(
    audit_log_id: int,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_main_db),
) -> dict:
    """按 ID 查看单条审计日志详情。"""
    log = await db.get(AuditLog, audit_log_id)
    if log is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计日志不存在",
        )

    return _audit_log_to_dict(log)
