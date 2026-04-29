r"""
文件位置: app/schemas/device.py
文件名称: device.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    设备数据相关的 Pydantic v2 请求/响应模型。
    覆盖三个接口：
      - POST /api/device/heartbeat  : 安卓脚本上报心跳
      - GET  /api/device/list       : PC 中控拉取设备列表
      - GET  /api/device/data       : PC 中控拉取单台设备详情

    game_data 字段使用 dict，各游戏自定义内容（不在此层校验具体字段）。

关联文档:
    [[01-网络验证系统/接入契约]]
    [[01-网络验证系统/Redis心跳落库策略]]

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── 心跳上报 ──────────────────────────────────────────────────

class HeartbeatRequest(BaseModel):
    device_fingerprint: str = Field(
        ...,
        min_length=4,
        max_length=256,
        description="设备唯一标识，与登录时的 device_fingerprint 一致",
        examples=["a1b2c3d4e5f6"],
    )
    status: str = Field(
        ...,
        pattern="^(running|idle|error)$",
        description="当前运行状态：running / idle / error",
        examples=["running"],
    )
    game_data: dict = Field(
        default_factory=dict,
        description="游戏自定义数据，各游戏字段不同，不在此层校验",
        examples=[{"map": "北境", "gold": 1024, "task": "日常采集"}],
    )


class HeartbeatResponse(BaseModel):
    code: int = 0
    message: str = "ok"


# ── 设备列表 ──────────────────────────────────────────────────

class DeviceStatus(BaseModel):
    device_id: str = Field(description="设备唯一标识")
    user_id: int
    status: str | None = Field(description="running / idle / error / offline")
    last_seen: datetime | None = Field(description="最后一次心跳时间")
    game_data: dict | None = Field(description="游戏自定义数据")
    is_online: bool = Field(
        description="True = Redis 中有活跃心跳（TTL 未过期）；"
                    "False = 仅在数据库中有历史记录"
    )


class DeviceListResponse(BaseModel):
    devices: list[DeviceStatus]
    total: int
    online_count: int


# ── 单台设备详情 ──────────────────────────────────────────────

class DeviceDataResponse(BaseModel):
    device_id: str
    user_id: int
    status: str | None
    last_seen: datetime | None
    game_data: dict | None
    is_online: bool
    source: str = Field(
        description="数据来源：redis（实时）/ database（落库数据）/ not_found",
        examples=["redis"],
    )


# ── T027 IMSI 后续上传 ──────────────────────────────

class ImsiUploadRequest(BaseModel):
    """
    登录成功后上传 IMSI 码（接入契约 §8）。
    IMSI 不参与登录验证，仅作为辅助设备标识存储。
    """
    device_fingerprint: str = Field(
        ...,
        description="主设备指纹（与登录时一致）",
    )
    imsi: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="设备 IMSI 码",
    )


class ImsiUploadResponse(BaseModel):
    message: str
    device_fingerprint: str
    imsi: str
