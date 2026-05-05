r"""
文件位置: tests/test_auth.py
名称: 认证模块集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-02
版本: V1.2.0
功能说明:
    认证模块集成测试。

    当前测试口径:
      1. 授权创建请求必须显式传入 Authorization.user_level。
      2. 授权创建请求必须显式传入 Authorization.authorized_devices。
      3. 登录响应中的 authorization_level 当前来自 Authorization.user_level。
      4. Refresh Token 刷新必须重新校验 Authorization。
      5. /api/auth/me 必须返回当前项目 Authorization 授权摘要。
      6. 软删除用户不得登录。
      7. 软删除用户不得使用 Refresh Token 刷新 Access Token。

    当前仍未覆盖的边界:
      1. Admin / Agent Token 服务端吊销不在本文件测试范围内。

改进历史:
    V1.2.0 (2026-05-02) - 同步 /api/auth/me 授权摘要结构。
    V1.1.0 (2026-05-02) - 授权测试改为 Authorization 口径；补软删除登录 / refresh 测试。
    V1.0.0 (2026-04-22) - 初始认证模块集成测试。
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import decode_access_token


PROJECT_UUID = "00000000-0000-0000-0000-000000000001"
PROJECT_CODE = "game_001"


async def _create_test_user(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
    *,
    user_level: str = "tester",
    authorized_devices: int = 0,
) -> dict:
    """
    创建测试用户并授予指定项目授权。

    注意:
      登录 / refresh / me 断言必须以 Authorization 为准。
    """
    suffix = uuid.uuid4().hex[:8]
    username = f"auth_test_{suffix}"
    password = "TestPass@2026!"

    create_user_response = await client.post(
        "/api/users/",
        json={
            "username": username,
            "password": password,
        },
        headers=admin_headers,
    )
    assert create_user_response.status_code == 201, (
        f"创建用户失败: {create_user_response.text}"
    )
    user_id = create_user_response.json()["id"]

    grant_auth_response = await client.post(
        f"/api/users/{user_id}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": user_level,
            "authorized_devices": authorized_devices,
            "valid_until": None,
        },
        headers=admin_headers,
    )
    assert grant_auth_response.status_code == 201, (
        f"授权失败: {grant_auth_response.text}"
    )

    return {
        "username": username,
        "password": password,
        "user_id": user_id,
        "authorization_id": grant_auth_response.json()["id"],
        "user_level": user_level,
        "authorized_devices": authorized_devices,
    }


async def _login_user(
    client: AsyncClient,
    *,
    username: str,
    password: str,
    device_fingerprint: str | None = None,
    client_type: str = "android",
):
    """执行用户登录请求。"""
    return await client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
            "project_uuid": PROJECT_UUID,
            "device_fingerprint": device_fingerprint or f"device_{uuid.uuid4().hex[:8]}",
            "client_type": client_type,
        },
    )


async def _set_user_soft_deleted(session_factory, user_id: int) -> None:
    """直接把用户标记为软删除，用于认证边界测试。"""
    async with session_factory() as session:
        await session.execute(
            text(
                'UPDATE "user" '
                "SET is_deleted = TRUE, status = 'active' "
                "WHERE id = :user_id"
            ),
            {"user_id": user_id},
        )
        await session.commit()


async def _set_authorization_level(
    session_factory,
    *,
    authorization_id: int,
    user_level: str,
) -> None:
    """直接修改 Authorization.user_level，用于验证 refresh 是否重新读取授权事实源。"""
    async with session_factory() as session:
        await session.execute(
            text(
                'UPDATE "authorization" '
                "SET user_level = :user_level "
                "WHERE id = :authorization_id"
            ),
            {
                "user_level": user_level,
                "authorization_id": authorization_id,
            },
        )
        await session.commit()


class TestLogin:
    async def test_login_success_uses_authorization_level(
        self,
        client,
        admin_headers,
        project_id,
    ):
        """正常登录应返回 AT/RT，且 user_level 来自 Authorization.user_level。"""
        user = await _create_test_user(
            client,
            admin_headers,
            project_id,
            user_level="tester",
            authorized_devices=0,
        )

        response = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            device_fingerprint="test_device_auth_001",
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "refresh_token" in data

        # 重点：
        # 这里必须返回 Authorization.user_level = tester。
        assert data["authorization_level"] == "tester"
        assert "user_level" not in data
        assert data["game_project_code"] == PROJECT_CODE

        payload = decode_access_token(data["access_token"])
        assert payload["authorization_level"] == "tester"
        assert payload["project_code"] == PROJECT_CODE

    async def test_login_wrong_password(self, client, admin_headers, project_id):
        """密码错误应返回 401。"""
        user = await _create_test_user(client, admin_headers, project_id)

        response = await _login_user(
            client,
            username=user["username"],
            password="WrongPassword!",
            device_fingerprint="device_wrong_password",
        )

        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client):
        """不存在的用户应返回 401。"""
        response = await _login_user(
            client,
            username="no_such_user_xyz",
            password="any_password",
            device_fingerprint="device_nonexistent",
        )

        assert response.status_code == 401

    async def test_login_invalid_project(self, client, admin_headers, project_id):
        """无效的 project_uuid 应返回 404。"""
        user = await _create_test_user(client, admin_headers, project_id)

        response = await client.post(
            "/api/auth/login",
            json={
                "username": user["username"],
                "password": user["password"],
                "project_uuid": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "device_fingerprint": "device_invalid_project",
                "client_type": "android",
            },
        )

        assert response.status_code == 404

    async def test_login_no_authorization(self, client, admin_headers):
        """未授权用户登录应返回 403。"""
        suffix = uuid.uuid4().hex[:8]
        username = f"no_auth_{suffix}"
        password = "TestPass@2026!"

        create_user_response = await client.post(
            "/api/users/",
            json={
                "username": username,
                "password": password,
            },
            headers=admin_headers,
        )
        assert create_user_response.status_code == 201

        response = await _login_user(
            client,
            username=username,
            password=password,
            device_fingerprint="device_no_auth",
        )

        assert response.status_code == 403

    async def test_login_suspended_user(self, client, admin_headers, project_id):
        """已停用的用户应返回 403。"""
        user = await _create_test_user(client, admin_headers, project_id)

        suspend_response = await client.patch(
            f"/api/users/{user['user_id']}",
            json={"status": "suspended"},
            headers=admin_headers,
        )
        assert suspend_response.status_code == 200

        response = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            device_fingerprint="device_suspended",
        )

        assert response.status_code == 403

    async def test_login_soft_deleted_user_is_rejected(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        """软删除用户即使 status=active，也不得登录。"""
        user = await _create_test_user(client, admin_headers, project_id)
        await _set_user_soft_deleted(session_factory, user["user_id"])

        response = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            device_fingerprint="device_soft_deleted_login",
        )

        assert response.status_code == 401


class TestRefreshAndMe:
    async def _do_login(
        self,
        client,
        admin_headers,
        project_id,
        *,
        user_level: str = "tester",
        authorized_devices: int = 0,
    ) -> dict:
        user = await _create_test_user(
            client,
            admin_headers,
            project_id,
            user_level=user_level,
            authorized_devices=authorized_devices,
        )

        response = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
        )

        assert response.status_code == 200

        return {
            **user,
            **response.json(),
        }

    async def test_get_me_returns_authorization_summary(
        self,
        client,
        admin_headers,
        project_id,
    ):
        """
        /api/auth/me 必须返回当前 Token 项目上下文下的 Authorization 授权摘要。
        """
        tokens = await self._do_login(
            client,
            admin_headers,
            project_id,
            user_level="tester",
            authorized_devices=0,
        )

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_id"] == tokens["user_id"]
        assert data["username"] == tokens["username"]
        assert data["status"] == "active"

        assert data["game_project_id"] == project_id
        assert data["game_project_code"] == PROJECT_CODE

        assert data["authorization_id"] == tokens["authorization_id"]
        assert data["authorization_level"] == "tester"
        assert data["authorized_devices"] == 0
        assert data["valid_until"] is None

        # 硬清理断言：
        # /me 不再返回旧 User.user_level 字段。
        assert "user_level" not in data

    async def test_refresh_uses_latest_authorization_level(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        """
        Refresh Token 刷新时必须重新读取 Authorization.user_level。

        构造:
          1. 初始 Authorization.user_level 为 tester。
          2. 登录后直接把 Authorization.user_level 改为 svip。
          3. refresh 后的新 Access Token 必须是 svip。
        """
        tokens = await self._do_login(
            client,
            admin_headers,
            project_id,
            user_level="tester",
            authorized_devices=0,
        )

        await _set_authorization_level(
            session_factory,
            authorization_id=tokens["authorization_id"],
            user_level="svip",
        )

        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert refresh_response.status_code == 200
        data = refresh_response.json()
        assert "access_token" in data

        payload = decode_access_token(data["access_token"])
        assert payload["authorization_level"] == "svip"
        assert payload["project_code"] == PROJECT_CODE

    async def test_refresh_soft_deleted_user_is_rejected(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        """软删除用户不得使用 Refresh Token 刷新 Access Token。"""
        tokens = await self._do_login(client, admin_headers, project_id)

        await _set_user_soft_deleted(session_factory, tokens["user_id"])

        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 401

    async def test_logout_then_me_fails(self, client, admin_headers, project_id):
        """登出后当前 Access Token 应被吊销，/me 返回 401。"""
        tokens = await self._do_login(client, admin_headers, project_id)
        at_header = {"Authorization": f"Bearer {tokens['access_token']}"}

        logout_response = await client.post(
            "/api/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=at_header,
        )
        assert logout_response.status_code == 200

        response = await client.get("/api/auth/me", headers=at_header)
        assert response.status_code == 401
