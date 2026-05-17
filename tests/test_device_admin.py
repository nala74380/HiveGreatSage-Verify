r"""
文件位置: tests/test_device_admin.py
名称: 管理后台设备监控集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-17
版本: V1.1.0
功能说明:
    测试后台设备监控链：
      GET /admin/api/devices/{game_project_code}

改进历史:
    V1.1.0 (2026-05-17) - 删除 IMSI 上传测试；对齐后台设备标识口径。
    V1.0.0 - 初始版本（T026 + T027）
"""

import uuid

from httpx import AsyncClient


from tests.conftest import GAME_PROJECT_CODE


async def _create_and_login(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    username = f"da_test_{suffix}"
    device_fp = f"da_dev_{uuid.uuid4().hex[:16]}"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": "Device@2026!",
    }, headers=admin_headers)
    assert r.status_code == 201
    user_id = r.json()["id"]

    await client.post(
        f"/api/users/{user_id}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": "normal",
            "authorized_devices": 20,
        },
        headers=admin_headers,
    )

    r = await client.post("/api/auth/login", json={
        "username": username,
        "password": "Device@2026!",
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_fingerprint": device_fp,
        "device_id": "A-001",
        "connection_type": "usb",
        "connection_label": "SN:TEST1234",
        "client_type": "android",
    })
    assert r.status_code == 200
    result = r.json()
    result["device_fingerprint"] = device_fp
    return result


class TestAdminDeviceList:
    async def test_requires_auth(self, client):
        r = await client.get(f"/admin/api/devices/{GAME_PROJECT_CODE}")
        assert r.status_code in (401, 403)

    async def test_admin_can_access(self, client, admin_headers):
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()

        assert "devices" in data
        assert "total" in data
        assert "online_count" in data
        assert "page" in data
        assert "page_size" in data
        assert "game_project_code" in data
        assert data["game_project_code"] == GAME_PROJECT_CODE
        assert isinstance(data["devices"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["online_count"], int)

    async def test_agent_can_access_own_scope(
        self, client, admin_headers, project_id
    ):
        suffix = uuid.uuid4().hex[:6]
        agent_name = f"da_agent_{suffix}"
        r = await client.post("/api/agents/", json={
            "username": agent_name,
            "password": "Agent@2026!",
        }, headers=admin_headers)
        assert r.status_code == 201

        r = await client.post("/api/agents/auth/login", json={
            "username": agent_name,
            "password": "Agent@2026!",
        })
        assert r.status_code == 200
        agent_token = r.json()["access_token"]

        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "devices" in data

    async def test_nonexistent_game_returns_404(self, client, admin_headers):
        r = await client.get(
            "/admin/api/devices/nonexistent_game_xyz",
            headers=admin_headers,
        )
        assert r.status_code == 404

    async def test_pagination_params(self, client, admin_headers):
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            params={"page": 1, "page_size": 5},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["devices"]) <= 5
        assert data["page_size"] == 5

    async def test_online_only_filter(self, client, admin_headers):
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            params={"online_only": "true"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        for device in data["devices"]:
            assert device["is_online"] is True

    async def test_device_has_required_fields(
        self, client, admin_headers, project_id
    ):
        login_data = await _create_and_login(client, admin_headers, project_id)
        user_token = login_data["access_token"]
        device_fp = login_data["device_fingerprint"]

        await client.post("/api/device/heartbeat", json={
            "device_fingerprint": device_fp,
            "device_id": "A-001",
            "connection_type": "usb",
            "connection_label": "SN:TEST1234",
            "status": "running",
            "game_data": {"test_key": "test_val"},
        }, headers={"Authorization": f"Bearer {user_token}"})

        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            params={"online_only": "true"},
            headers=admin_headers,
        )
        data = r.json()

        our_device = next(
            (d for d in data["devices"] if d.get("device_fingerprint") == device_fp),
            None,
        )
        assert our_device is not None, "刚上报的设备未出现在监控列表中"
        assert our_device["device_id"] == "A-001"
        assert our_device["device_fingerprint"] == device_fp
        assert our_device["connection_type"] == "usb"
        assert our_device["connection_label"] == "SN:TEST1234"
        assert "user_id" in our_device
        assert "username" in our_device
        assert "status" in our_device
        assert "is_online" in our_device
        assert "source" in our_device
        assert our_device["is_online"] is True
        assert our_device["status"] == "running"
