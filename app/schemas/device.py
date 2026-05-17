r"""
文件位置: app/schemas/device.py
文件名称: device.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-17
版本: V1.2.0
功能说明:
    设备数据相关的 Pydantic v2 请求/响应模型。
    覆盖三个接口：
      - POST /api/device/heartbeat  : 安卓脚本上报心跳
      - GET  /api/device/list       : PC 中控拉取设备列表
      - GET  /api/device/data       : PC 中控拉取单台设备详情

    当前设备标识口径：
      1. device_fingerprint = 设备内部稳定绑定键。
      2. device_id = 用户自定义设备编号（业务展示字段）。
      3. connection_type / connection_label = 连接标识。

改进历史:
    V1.2.0 (2026-05-17) - 删除 IMSI 上传契约；新增 device_id / connection_type / connection_label 字段。
    V1.1.0 (2026-05-07) - ImsiUploadResponse 移除 device_fingerprint / imsi 原文回显。
    V1.0.0 - 初始版本
"""

from datetime import datetime

from pydantic import BaseModel, Field


class HeartbeatRequest(BaseModel):
    device_fingerprint: str = Field(
        ...,
        min_length=4,
        max_length=256,
        description="设备内部稳定绑定键，与登录时的 device_fingerprint 一致",
        examples=["a1b2c3d4e5f6"],
    )
    device_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="用户自定义设备编号（业务展示字段）",
        examples=["A-001"],
    )
    connection_type: str | None = Field(
        default=None,
        description="连接类型：usb / tcp / unknown",
        examples=["usb"],
        pattern="^(usb|tcp|unknown)$",
    )
    connection_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="连接标识展示串：USB 显示 SN，TCP 显示 IP:端口",
        examples=["SN:ABCD1234"],
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


class DeviceStatus(BaseModel):
    device_fingerprint: str = Field(description="设备内部稳定绑定键")
    device_id: str | None = Field(default=None, description="用户自定义设备编号")
    connection_type: str | None = Field(default=None, description="连接类型：usb / tcp / unknown")
    connection_label: str | None = Field(default=None, description="连接标识展示串")
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


class DeviceDataResponse(BaseModel):
    device_fingerprint: str
    device_id: str | None = None
    connection_type: str | None = None
    connection_label: str | None = None
    user_id: int
    status: str | None
    last_seen: datetime | None
    game_data: dict | None
    is_online: bool
    source: str = Field(
        description="数据来源：redis（实时）/ database（落库数据）/ not_found",
        examples=["redis"],
    )
