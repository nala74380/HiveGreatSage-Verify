r"""
文件位置: app/schemas/stats.py
名称: 统计数据 Pydantic 模型
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-28
版本: V1.0.0
功能说明:
    用户/代理管理后台所需的各类统计聚合模型。

    覆盖：
      - UserProjectStats     用户×项目维度的设备激活统计
      - AgentProjectSummary  代理视角的项目用户统计
      - PlatformSummary      管理员全平台概览统计
"""

from pydantic import BaseModel, Field
from datetime import datetime


# ── 用户×项目维度统计 ─────────────────────────────────────────

class DeviceStatsByProject(BaseModel):
    """单个项目下，该用户的设备绑定/激活统计。"""
    game_project_id:   int
    game_project_code: str
    game_project_name: str
    authorization_status: str   # active / suspended
    valid_until: datetime | None

    # 设备维度
    total_bound:   int = Field(description="已绑定设备数（status=active 的 device_binding）")
    activated:     int = Field(description="已激活设备数（device_binding.imsi 非空 或 activated 标记）")
    not_activated: int = Field(description="未激活设备数（total_bound - activated）")
    online_now:    int = Field(default=0, description="当前在线设备数（来自 Redis，可选）")


class UserProjectStatsResponse(BaseModel):
    """用户的项目授权统计响应。"""
    user_id:       int
    username:      str
    user_level:    str
    project_stats: list[DeviceStatsByProject]

    # 汇总
    total_projects:      int = Field(description="授权的游戏项目总数")
    active_projects:     int = Field(description="有效授权的项目数")
    total_devices_bound: int = Field(description="全部项目绑定设备总数")
    total_activated:     int = Field(description="全部项目已激活设备总数")
    total_not_activated: int = Field(description="全部项目未激活设备总数")


# ── 代理视角项目统计 ───────────────────────────────────────────

class ProjectUserCount(BaseModel):
    """代理权限范围内，某项目的用户/授权统计。"""
    game_project_id:   int
    game_project_code: str
    game_project_name: str
    user_count:        int = Field(description="该代理权限范围内持有该项目授权的用户数")
    authorization_count: int = Field(description="该项目授权总数（含 suspended）")
    active_authorization_count: int = Field(description="有效授权数量")
    total_devices:     int = Field(description="该项目下所有用户的绑定设备总数")
    activated_devices: int = Field(description="已激活设备总数")


class AgentProjectSummaryResponse(BaseModel):
    """代理视角：我管辖范围内各项目的用户/授权/设备统计。"""
    agent_id:       int
    agent_username: str
    scope_agent_count: int = Field(description="权限范围内代理总数（含自身）")
    scope_user_count:  int = Field(description="权限范围内用户总数")
    project_summaries: list[ProjectUserCount]


# ── 管理员全平台概览 ─────────────────────────────────────────

class PlatformSummaryResponse(BaseModel):
    """管理员全平台概览统计（首页 Dashboard 用）。"""
    total_users:       int
    active_users:      int
    total_agents:      int
    total_projects:    int
    total_devices_bound: int
    total_devices_online: int   # 来自 Redis，实时值
    total_authorizations: int
    # 按级别分布
    level_distribution: dict[str, int] = Field(
        description="各级别用户数，如 {'normal': 100, 'vip': 30}"
    )
