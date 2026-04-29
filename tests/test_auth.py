r"""
文件位置: tests/test_auth.py
名称: 认证模块集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-22
版本: V1.0.0
"""

import uuid
import pytest
from httpx import AsyncClient


async def _create_test_user(client: AsyncClient, admin_headers: dict, project_id: int) -> dict:
    """辅助函数：创建测试用户并授权，返回 {username, password, project_uuid}。"""
    suffix = uuid.uuid4().hex[:8]
    username = f"auth_test_{suffix}"
    password = "TestPass@2026!"

    # 创建用户
    r = await client.post("/api/users/", json={
        "username": username,
        "password": password,
        "user_level": "tester",
    }, headers=admin_headers)
    assert r.status_code == 201, f"创建用户失败: {r.text}"
    user_id = r.json()["id"]

    # 授权
    r = await client.post(f"/api/users/{user_id}/authorizations", json={
        "game_project_id": project_id,
    }, headers=admin_headers)
    assert r.status_code == 201, f"授权失败: {r.text}"

    return {
        "username": username,
        "password": password,
        "user_id": user_id,
    }


class TestLogin:
    async def test_login_success(self, client, admin_headers, project_id):
        """正常登录应返回 access_token 和 refresh_token。"""
        user = await _create_test_user(client, admin_headers, project_id)
        r = await client.post("/api/auth/login", json={
            "username": user["username"],
            "password": user["password"],
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": "test_device_auth_001",
            "client_type": "android",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user_level"] == "tester"
        assert data["game_project_code"] == "game_001"

    async def test_login_wrong_password(self, client, admin_headers, project_id):
        """密码错误应返回 401。"""
        user = await _create_test_user(client, admin_headers, project_id)
        r = await client.post("/api/auth/login", json={
            "username": user["username"],
            "password": "WrongPassword!",
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": "device_001",
            "client_type": "android",
        })
        assert r.status_code == 401

    async def test_login_nonexistent_user(self, client):
        """不存在的用户应返回 401。"""
        r = await client.post("/api/auth/login", json={
            "username": "no_such_user_xyz",
            "password": "any_password",
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": "device_001",
            "client_type": "android",
        })
        assert r.status_code == 401

    async def test_login_invalid_project(self, client, admin_headers, project_id):
        """无效的 project_uuid 应返回 404。"""
        user = await _create_test_user(client, admin_headers, project_id)
        r = await client.post("/api/auth/login", json={
            "username": user["username"],
            "password": user["password"],
            "project_uuid": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "device_fingerprint": "device_001",
            "client_type": "android",
        })
        assert r.status_code == 404

    async def test_login_no_authorization(self, client, admin_headers):
        """未授权用户登录应返回 403。"""
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"no_auth_{suffix}",
            "password": "Test@2026!",
            "user_level": "normal",
        }, headers=admin_headers)
        assert r.status_code == 201

        r = await client.post("/api/auth/login", json={
            "username": f"no_auth_{suffix}",
            "password": "Test@2026!",
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": "device_001",
            "client_type": "android",
        })
        assert r.status_code == 403

    async def test_login_suspended_user(self, client, admin_headers, project_id):
        """已停用的用户应返回 403。"""
        user = await _create_test_user(client, admin_headers, project_id)

        # 停用
        await client.patch(f"/api/users/{user['user_id']}",
                          json={"status": "suspended"},
                          headers=admin_headers)

        r = await client.post("/api/auth/login", json={
            "username": user["username"],
            "password": user["password"],
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": "device_001",
            "client_type": "android",
        })
        assert r.status_code == 403


class TestRefreshAndLogout:
    async def _do_login(self, client, admin_headers, project_id) -> dict:
        user = await _create_test_user(client, admin_headers, project_id)
        r = await client.post("/api/auth/login", json={
            "username": user["username"],
            "password": user["password"],
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": f"device_{uuid.uuid4().hex[:8]}",
            "client_type": "android",
        })
        assert r.status_code == 200
        return r.json()

    async def test_get_me(self, client, admin_headers, project_id):
        """持有有效 Token 应能获取当前用户信息。"""
        tokens = await self._do_login(client, admin_headers, project_id)
        r = await client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["user_level"] == "tester"
        assert data["game_project_code"] == "game_001"

    async def test_logout_then_me_fails(self, client, admin_headers, project_id):
        """登出后 Token 应被吊销，/me 返回 401。"""
        tokens = await self._do_login(client, admin_headers, project_id)
        at_header = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 登出
        r = await client.post("/api/auth/logout",
                              json={"refresh_token": tokens["refresh_token"]},
                              headers=at_header)
        assert r.status_code == 200

        # 再次调用 /me 应返回 401
        r = await client.get("/api/auth/me", headers=at_header)
        assert r.status_code == 401