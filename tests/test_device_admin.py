r"""
文件位置: tests/test_device_admin.py
名称: 管理后台设备监控 + IMSI 上传集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    测试 T026 和 T027：
      GET  /admin/api/devices/{game_project_code} — 管理后台设备监控
      POST /api/device/imsi                       — IMSI 后续上传

    注意：
      T026 需要设备已上报过心跳（Redis 中有数据）或游戏库中有 device_runtime 记录。
      由于 test_device.py 中的 test_heartbeat_success 会写入 Redis，
      若在同一测试 session 中运行，Redis 中会有数据可查。
      但 Redis 数据有 TTL=120s，跨 session 运行时 T026 可能返回空设备列表，
      测试中只断言接口返回正确结构，不断言设备数量。

改进历史:
    V1.0.0 - 初始版本（T026 + T027）
"""

import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import GAME_PROJECT_CODE, ADMIN_USERNAME, ADMIN_PASSWORD


# ── 辅助：创建用户 + 登录 + 返回登录结果 ──────────────────────

async def _create_and_login(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
) -> dict:
    """创建用户 → 授权 → 登录，返回完整登录响应 dict（含 access_token + device_fingerprint）。"""
    suffix = uuid.uuid4().hex[:8]
    username = f"da_test_{suffix}"
    device_fp = f"da_dev_{uuid.uuid4().hex[:16]}"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": "Device@2026!",
        "user_level": "tester",
    }, headers=admin_headers)
    assert r.status_code == 201
    user_id = r.json()["id"]

    await client.post(
        f"/api/users/{user_id}/authorizations",
        json={"game_project_id": project_id},
        headers=admin_headers,
    )

    r = await client.post("/api/auth/login", json={
        "username": username,
        "password": "Device@2026!",
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_fingerprint": device_fp,
        "client_type": "android",
    })
    assert r.status_code == 200
    result = r.json()
    result["device_fingerprint"] = device_fp
    return result


# ──────────────────────────────────────────────────────────────
# T026 — 管理后台设备监控
# ──────────────────────────────────────────────────────────────

class TestAdminDeviceList:
    async def test_requires_auth(self, client):
        """无 Token 应返回 401/403。"""
        r = await client.get(f"/admin/api/devices/{GAME_PROJECT_CODE}")
        assert r.status_code in (401, 403)

    async def test_admin_can_access(self, client, admin_headers):
        """Admin Token 应返回 200，响应结构正确。"""
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()

        # 验证响应结构
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
        """Agent Token 应返回 200（只查看权限范围内设备）。"""
        # 创建一个代理
        suffix = uuid.uuid4().hex[:6]
        agent_name = f"da_agent_{suffix}"
        r = await client.post("/api/agents/", json={
            "username": agent_name,
            "password": "Agent@2026!",
            "max_users": 10,
        }, headers=admin_headers)
        assert r.status_code == 201

        # 代理登录
        r = await client.post("/api/agents/auth/login", json={
            "username": agent_name,
            "password": "Agent@2026!",
        })
        assert r.status_code == 200
        agent_token = r.json()["access_token"]

        # 代理访问设备监控
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "devices" in data

    async def test_nonexistent_game_returns_404(self, client, admin_headers):
        """不存在的游戏项目应返回 404。"""
        r = await client.get(
            "/admin/api/devices/nonexistent_game_xyz",
            headers=admin_headers,
        )
        assert r.status_code == 404

    async def test_pagination_params(self, client, admin_headers):
        """分页参数正常生效，page_size=5 时 devices 数量 ≤ 5。"""
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
        """online_only=true 时所有返回设备的 is_online 均为 True。"""
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
        """
        上报一次心跳后，设备监控应返回含完整字段的设备记录。
        各字段：device_id / user_id / username / status / is_online / source。
        """
        login_data = await _create_and_login(client, admin_headers, project_id)
        user_token = login_data["access_token"]
        device_fp = login_data["device_fingerprint"]

        # 上报一次心跳
        await client.post("/api/device/heartbeat", json={
            "device_fingerprint": device_fp,
            "status": "running",
            "game_data": {"test_key": "test_val"},
        }, headers={"Authorization": f"Bearer {user_token}"})

        # 查设备列表
        r = await client.get(
            f"/admin/api/devices/{GAME_PROJECT_CODE}",
            params={"online_only": "true"},
            headers=admin_headers,
        )
        data = r.json()

        # 找到刚刚上报心跳的设备
        our_device = next(
            (d for d in data["devices"] if d["device_id"] == device_fp),
            None,
        )
        assert our_device is not None, "刚上报的设备未出现在监控列表中"
        assert "device_id" in our_device
        assert "user_id" in our_device
        assert "username" in our_device
        assert "status" in our_device
        assert "is_online" in our_device
        assert "source" in our_device
        assert our_device["is_online"] is True
        assert our_device["status"] == "running"


# ──────────────────────────────────────────────────────────────
# T027 — IMSI 后续上传
# ──────────────────────────────────────────────────────────────

class TestImsiUpload:
    async def test_imsi_requires_auth(self, client):
        r = await client.post("/api/device/imsi", json={
            "device_fingerprint": "test_fp",
            "imsi": "460001234567890",
        })
        assert r.status_code == 403

    async def test_imsi_upload_success(
        self, client, admin_headers, project_id
    ):
        """登录后上传 IMSI，应返回 200 并回显 IMSI 值。"""
        login_data = await _create_and_login(client, admin_headers, project_id)
        token = login_data["access_token"]
        device_fp = login_data["device_fingerprint"]

        r = await client.post("/api/device/imsi", json={
            "device_fingerprint": device_fp,
            "imsi": "460001234567890",
        }, headers={"Authorization": f"Bearer {token}"})

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["imsi"] == "460001234567890"
        assert data["device_fingerprint"] == device_fp
        assert "message" in data

    async def test_imsi_upload_unbound_device_fails(
        self, client, admin_headers, project_id
    ):
        """为未绑定的设备上传 IMSI 应返回 404。"""
        login_data = await _create_and_login(client, admin_headers, project_id)
        token = login_data["access_token"]

        r = await client.post("/api/device/imsi", json={
            "device_fingerprint": "nonexistent_device_fp_xyz",
            "imsi": "460001234567890",
        }, headers={"Authorization": f"Bearer {token}"})

        assert r.status_code == 404

    async def test_imsi_overwrite(
        self, client, admin_headers, project_id
    ):
        """IMSI 可重复上传（覆盖旧值），应返回 200。"""
        login_data = await _create_and_login(client, admin_headers, project_id)
        token = login_data["access_token"]
        device_fp = login_data["device_fingerprint"]
        headers = {"Authorization": f"Bearer {token}"}

        # 第一次上传
        await client.post("/api/device/imsi", json={
            "device_fingerprint": device_fp,
            "imsi": "460001111111111",
        }, headers=headers)

        # 第二次上传（覆盖）
        r = await client.post("/api/device/imsi", json={
            "device_fingerprint": device_fp,
            "imsi": "460002222222222",
        }, headers=headers)

        assert r.status_code == 200
        assert r.json()["imsi"] == "460002222222222"

    async def test_imsi_empty_string_fails(
        self, client, admin_headers, project_id
    ):
        """IMSI 为空字符串应返回 422（min_length=1）。"""
        login_data = await _create_and_login(client, admin_headers, project_id)
        token = login_data["access_token"]
        device_fp = login_data["device_fingerprint"]

        r = await client.post("/api/device/imsi", json={
            "device_fingerprint": device_fp,
            "imsi": "",
        }, headers={"Authorization": f"Bearer {token}"})

        assert r.status_code == 422
