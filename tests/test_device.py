r"""
文件位置: tests/test_device.py
名称: 设备数据模块集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-22
版本: V1.0.0
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.main.models import DeviceBinding


async def _login(client: AsyncClient, admin_headers: dict, project_id: int) -> dict:
    suffix = uuid.uuid4().hex[:8]
    username = f"dev_test_{suffix}"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": "DevTest@2026!",
    }, headers=admin_headers)
    assert r.status_code == 201, f"用户创建失败: {r.status_code} | {r.text}"
    user_id = r.json()["id"]

    r2 = await client.post(
        f"/api/users/{user_id}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": "normal",
            "authorized_devices": 20,
        },
        headers=admin_headers,
    )
    assert r2.status_code == 201, f"授权失败: {r2.status_code} | {r2.text}"

    device_fp = f"dev_{uuid.uuid4().hex[:12]}"
    r3 = await client.post("/api/auth/login", json={
        "username": username,
        "password": "DevTest@2026!",
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_fingerprint": device_fp,
        "client_type": "android",
    })
    assert r3.status_code == 200, f"登录失败: {r3.status_code} | {r3.text}"
    return {"access_token": r3.json()["access_token"], "device_fp": device_fp, "user_id": user_id}


class TestHeartbeat:
    async def test_heartbeat_success(self, client, admin_headers, project_id):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        r = await client.post("/api/device/heartbeat", json={
            "device_fingerprint": session["device_fp"],
            "status": "running",
            "game_data": {"map": "北境", "gold": 1024},
        }, headers=headers)
        assert r.status_code == 200
        assert r.json()["code"] == 0

    async def test_heartbeat_does_not_write_main_db_last_seen(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        """心跳请求链路只写 Redis，主库 last_seen_at 由 Celery 批量回写。"""
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        async with session_factory() as db:
            before_result = await db.execute(
                select(DeviceBinding.last_seen_at).where(
                    DeviceBinding.user_id == session["user_id"],
                    DeviceBinding.game_project_id == project_id,
                    DeviceBinding.device_fingerprint == session["device_fp"],
                )
            )
            before_last_seen = before_result.scalar_one()

        r = await client.post("/api/device/heartbeat", json={
            "device_fingerprint": session["device_fp"],
            "status": "running",
            "game_data": {"gold": 2048},
        }, headers=headers)
        assert r.status_code == 200

        async with session_factory() as db:
            after_result = await db.execute(
                select(DeviceBinding.last_seen_at).where(
                    DeviceBinding.user_id == session["user_id"],
                    DeviceBinding.game_project_id == project_id,
                    DeviceBinding.device_fingerprint == session["device_fp"],
                )
            )
            after_last_seen = after_result.scalar_one()

        assert after_last_seen == before_last_seen

    async def test_heartbeat_wrong_device(self, client, admin_headers, project_id):
        """上报未绑定的设备指纹应返回 403。"""
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        r = await client.post("/api/device/heartbeat", json={
            "device_fingerprint": "fake_device_not_bound",
            "status": "running",
            "game_data": {},
        }, headers=headers)
        assert r.status_code == 403

    async def test_heartbeat_requires_auth(self, client):
        r = await client.post("/api/device/heartbeat", json={
            "device_fingerprint": "any",
            "status": "running",
            "game_data": {},
        })
        assert r.status_code == 403


class TestDeviceList:
    async def test_device_list_after_heartbeat(self, client, admin_headers, project_id):
        """上报心跳后，设备列表中应能看到该设备（is_online=True）。"""
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        # 先上报心跳
        await client.post("/api/device/heartbeat", json={
            "device_fingerprint": session["device_fp"],
            "status": "idle",
            "game_data": {"level": 50},
        }, headers=headers)

        # 拉取列表
        r = await client.get("/api/device/list", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["online_count"] >= 1

        online_devices = [d for d in data["devices"] if d["is_online"]]
        assert any(d["device_id"] == session["device_fp"] for d in online_devices)

    async def test_device_data_after_heartbeat(self, client, admin_headers, project_id):
        """上报心跳后，单台设备详情中应能读到 game_data。"""
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        await client.post("/api/device/heartbeat", json={
            "device_fingerprint": session["device_fp"],
            "status": "running",
            "game_data": {"task": "采集", "gold": 9999},
        }, headers=headers)

        r = await client.get(f"/api/device/data?device_fingerprint={session['device_fp']}",
                             headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["is_online"] is True
        assert data["source"] == "redis"
        assert data["game_data"]["gold"] == 9999
