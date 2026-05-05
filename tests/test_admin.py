r"""
文件位置: tests/test_admin.py
名称: 管理员 + 用户/代理管理集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-22
版本: V1.0.0
"""

import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import ADMIN_USERNAME, ADMIN_PASSWORD


class TestAdminLogin:
    async def test_admin_login_success(self, client):
        r = await client.post("/admin/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["username"] == ADMIN_USERNAME

    async def test_admin_login_wrong_password(self, client):
        r = await client.post("/admin/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": "wrong!",
        })
        assert r.status_code == 401

    async def test_dashboard_requires_token(self, client):
        r = await client.get("/admin/api/dashboard")
        assert r.status_code == 403

    async def test_dashboard_success(self, client, admin_headers):
        r = await client.get("/admin/api/dashboard", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_users" in data
        assert "total_agents" in data


class TestUserManagement:
    async def test_create_normal_user(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"normal_{suffix}",
            "password": "Pass@2026!",
        }, headers=admin_headers)
        assert r.status_code == 201
        data = r.json()
        assert "user_level" not in data
        assert data["created_by_admin"] is True

    async def test_create_user_rejects_old_level_field(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"tester_{suffix}",
            "password": "Pass@2026!",
            "user_level": "tester",
        }, headers=admin_headers)
        assert r.status_code == 422

    async def test_duplicate_username_fails(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        body = {"username": f"dup_{suffix}", "password": "P@2026!"}
        r1 = await client.post("/api/users/", json=body, headers=admin_headers)
        assert r1.status_code == 201
        r2 = await client.post("/api/users/", json=body, headers=admin_headers)
        assert r2.status_code == 409

    async def test_list_users(self, client, admin_headers):
        r = await client.get("/api/users/", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "users" in data
        assert "total" in data

    async def test_get_user_detail(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"detail_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)
        user_id = r.json()["id"]

        r = await client.get(f"/api/users/{user_id}", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == user_id
        assert "user_level" not in data

    async def test_update_user_status(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"upd_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)
        user_id = r.json()["id"]

        r = await client.patch(f"/api/users/{user_id}",
                               json={"status": "suspended"},
                               headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "suspended"

    async def test_grant_and_revoke_authorization(self, client, admin_headers, project_id):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/users/", json={
            "username": f"authtest_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)
        user_id = r.json()["id"]

        # 授权
        r = await client.post(
            f"/api/users/{user_id}/authorizations",
            json={
                "game_project_id": project_id,
                "user_level": "normal",
                "authorized_devices": 20,
            },
            headers=admin_headers,
        )
        assert r.status_code == 201
        auth_id = r.json()["id"]

        # 查看详情确认授权存在
        r = await client.get(f"/api/users/{user_id}", headers=admin_headers)
        auths = r.json()["authorizations"]
        assert any(a["id"] == auth_id for a in auths)

        # 撤销
        r = await client.delete(f"/api/users/{user_id}/authorizations/{auth_id}",
                                headers=admin_headers)
        assert r.status_code == 204

    async def test_user_not_found(self, client, admin_headers):
        r = await client.get("/api/users/99999999", headers=admin_headers)
        assert r.status_code == 404

    async def test_requires_auth(self, client):
        r = await client.get("/api/users/")
        assert r.status_code == 403


class TestAgentManagement:
    async def test_create_agent(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/agents/", json={
            "username": f"agent_{suffix}",
            "password": "Agent@2026!",
        }, headers=admin_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["level"] == 1
        assert data["parent_agent_id"] is None

    async def test_create_sub_agent(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/agents/", json={
            "username": f"parent_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)
        parent_id = r.json()["id"]

        r = await client.post("/api/agents/", json={
            "username": f"child_{suffix}",
            "password": "P@2026!",
            "parent_agent_id": parent_id,
        }, headers=admin_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["level"] == 2
        assert data["parent_agent_id"] == parent_id

    async def test_agent_login_and_create_user(self, client, admin_headers):
        """代理登录后创建用户，用户应绑定到该代理。"""
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/agents/", json={
            "username": f"aglogin_{suffix}",
            "password": "Agent@2026!",
        }, headers=admin_headers)
        assert r.status_code == 201
        agent_id = r.json()["id"]

        # 代理登录
        r = await client.post("/api/agents/auth/login", json={
            "username": f"aglogin_{suffix}",
            "password": "Agent@2026!",
        })
        assert r.status_code == 200
        agent_token = r.json()["access_token"]
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # 代理创建用户
        r = await client.post("/api/users/", json={
            "username": f"aguser_{suffix}",
            "password": "User@2026!",
        }, headers=agent_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["created_by_agent_id"] == agent_id
        assert data["created_by_admin"] is False

    async def test_agent_cannot_create_tester(self, client, admin_headers, project_id):
        """代理创建用户成功（201），但授权 tester 级别被拒绝（403）。"""
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/agents/", json={
            "username": f"aglimit_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)

        r = await client.post("/api/agents/auth/login", json={
            "username": f"aglimit_{suffix}",
            "password": "P@2026!",
        })
        agent_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 代理可以创建用户（user_level 已从 User 模型迁移到 Authorization）
        r = await client.post("/api/users/", json={
            "username": f"tester_{suffix}",
            "password": "P@2026!",
        }, headers=agent_headers)
        assert r.status_code == 201
        user_id = r.json()["id"]

        # 但代理不能授予 tester 级别授权
        r = await client.post(f"/api/users/{user_id}/authorizations", json={
            "game_project_id": project_id,
            "user_level": "tester",
            "authorized_devices": 5,
            "valid_until": "2099-01-01T00:00:00Z",
        }, headers=agent_headers)
        assert r.status_code == 403

    async def test_list_agents(self, client, admin_headers):
        r = await client.get("/api/agents/", headers=admin_headers)
        assert r.status_code == 200
        assert "agents" in r.json()

    async def test_update_agent(self, client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        r = await client.post("/api/agents/", json={
            "username": f"agupd_{suffix}",
            "password": "P@2026!",
        }, headers=admin_headers)
        agent_id = r.json()["id"]

        r = await client.patch(
            f"/api/agents/{agent_id}",
            json={"status": "suspended", "commission_rate": 12.5},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "suspended"
        assert data["commission_rate"] == 12.5
