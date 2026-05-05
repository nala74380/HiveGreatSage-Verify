r"""
文件位置: tests/test_authorization_upgrade.py
名称: 授权升级接口测试
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-05-06
版本: V1.0.0
功能及相关说明:
  覆盖授权升级预览与升级接口的鉴权边界。

改进内容:
  V1.0.0 - 补充 upgrade preview 不允许匿名访问的回归测试。

调试信息:
  本文件只依赖主库，不依赖游戏库。
"""

import uuid


async def _create_user_with_authorization(client, admin_headers: dict, project_id: int) -> dict:
    username = f"upgrade_test_{uuid.uuid4().hex[:8]}"
    password = "TestPass@2026!"

    user_response = await client.post(
        "/api/users/",
        json={"username": username, "password": password},
        headers=admin_headers,
    )
    assert user_response.status_code == 201, user_response.text
    user = user_response.json()

    auth_response = await client.post(
        f"/api/users/{user['id']}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": "tester",
            "authorized_devices": 1,
            "valid_until": None,
        },
        headers=admin_headers,
    )
    assert auth_response.status_code == 201, auth_response.text
    auth = auth_response.json()

    return {"user_id": user["id"], "auth_id": auth["id"]}


class TestAuthorizationUpgradePreview:
    async def test_preview_requires_admin_or_agent_token(self, client, admin_headers, project_id):
        """授权升级预览不得匿名访问。"""
        item = await _create_user_with_authorization(client, admin_headers, project_id)

        response = await client.get(
            f"/api/users/{item['user_id']}/authorizations/{item['auth_id']}/upgrade/preview",
            params={"additional_devices": 1, "mode": "append"},
        )

        assert response.status_code == 401

    async def test_admin_can_preview_upgrade(self, client, admin_headers, project_id):
        """管理员可以预览授权升级；管理员预览不扣点。"""
        item = await _create_user_with_authorization(client, admin_headers, project_id)

        response = await client.get(
            f"/api/users/{item['user_id']}/authorizations/{item['auth_id']}/upgrade/preview",
            params={"additional_devices": 2, "mode": "append"},
            headers=admin_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["old_devices"] == 1
        assert data["new_devices"] == 3
        assert data["additional_devices"] == 2
        assert data["mode"] == "append"
        assert data["consumed_points"] == 0.0
