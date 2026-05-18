r"""
文件位置: tests/test_device.py
名称: 设备数据模块集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-17
版本: V1.1.0
功能说明:
    设备终端链集成测试。

当前设备标识口径：
    1. 账号 + 项目 + device_id 是设备绑定身份。

改进历史:
    V1.1.0 (2026-05-17) - 删除旧设备标识假设；补 device_id 主绑定规则断言。
    V1.0.0 - 初始版本
"""

import uuid
from httpx import AsyncClient
from sqlalchemy import select

from app.models.main.models import DeviceBinding
from tests.conftest import SECOND_GAME_PROJECT_UUID


def _idem(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _heartbeat_payload(device_id: str, *, status: str, game_data: dict) -> dict:
    return {
        "device_id": device_id,
        "status": status,
        "game_data": game_data,
    }


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
        headers={**admin_headers, "Idempotency-Key": _idem("grant")},
    )
    assert r2.status_code == 201, f"授权失败: {r2.status_code} | {r2.text}"

    authorization_id = r2.json()["id"]
    device_id = f"A-{uuid.uuid4().hex[:8]}"
    r3 = await client.post("/api/auth/login", json={
        "username": username,
        "password": "DevTest@2026!",
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_id": device_id,
        "client_type": "android",
    })
    assert r3.status_code == 200, f"登录失败: {r3.status_code} | {r3.text}"
    return {
        "access_token": r3.json()["access_token"],
        "device_id": device_id,
        "user_id": user_id,
        "authorization_id": authorization_id,
    }


async def _create_user_with_authorization(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
    *,
    username_prefix: str = "dev_test",
    authorized_devices: int = 20,
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    username = f"{username_prefix}_{suffix}"
    password = "DevTest@2026!"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": password,
    }, headers=admin_headers)
    assert r.status_code == 201, f"用户创建失败: {r.status_code} | {r.text}"
    user_id = r.json()["id"]

    r2 = await client.post(
        f"/api/users/{user_id}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": "normal",
            "authorized_devices": authorized_devices,
        },
        headers={**admin_headers, "Idempotency-Key": _idem("grant")},
    )
    assert r2.status_code == 201, f"授权失败: {r2.status_code} | {r2.text}"

    return {
        "user_id": user_id,
        "username": username,
        "password": password,
        "authorization_id": r2.json()["id"],
    }


async def _login_user(
    client: AsyncClient,
    *,
    username: str,
    password: str,
    project_uuid: str,
    device_id: str,
    client_type: str,
):
    return await client.post("/api/auth/login", json={
        "username": username,
        "password": password,
        "project_uuid": project_uuid,
        "device_id": device_id,
        "client_type": client_type,
    })


class TestHeartbeat:
    async def test_heartbeat_success(self, client, admin_headers, project_id):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        r = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(session["device_id"], status="running", game_data={"map": "北境", "gold": 1024}),
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0

    async def test_heartbeat_updates_main_db_last_seen(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        async with session_factory() as db:
            before_result = await db.execute(
                select(DeviceBinding.last_seen_at).where(
                    DeviceBinding.user_id == session["user_id"],
                    DeviceBinding.game_project_id == project_id,
                    DeviceBinding.device_id == session["device_id"],
                )
            )
            before_last_seen = before_result.scalar_one()

        r = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(session["device_id"], status="running", game_data={"gold": 2048}),
            headers=headers,
        )
        assert r.status_code == 200

        async with session_factory() as db:
            after_result = await db.execute(
                select(DeviceBinding.last_seen_at).where(
                    DeviceBinding.user_id == session["user_id"],
                    DeviceBinding.game_project_id == project_id,
                    DeviceBinding.device_id == session["device_id"],
                )
            )
            after_last_seen = after_result.scalar_one()

        assert after_last_seen is not None
        assert after_last_seen >= before_last_seen

    async def test_heartbeat_wrong_device(self, client, admin_headers, project_id):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        r = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload("fake_device_not_bound", status="running", game_data={}),
            headers=headers,
        )
        assert r.status_code == 403

    async def test_heartbeat_requires_auth(self, client):
        r = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload("any", status="running", game_data={}),
        )
        assert r.status_code == 403


class TestProjectScopedBindings:
    async def test_pc_login_does_not_create_android_device_binding(
        self,
        client,
        admin_headers,
        project_id,
        session_factory,
    ):
        user = await _create_user_with_authorization(
            client,
            admin_headers,
            project_id,
            authorized_devices=1,
        )
        pc_device_id = f"pc_{uuid.uuid4().hex[:12]}"

        response = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            project_uuid="00000000-0000-0000-0000-000000000001",
            device_id=pc_device_id,
            client_type="pc",
        )
        assert response.status_code == 200, response.text

        async with session_factory() as db:
            result = await db.execute(
                select(DeviceBinding).where(
                    DeviceBinding.user_id == user["user_id"],
                    DeviceBinding.game_project_id == project_id,
                    DeviceBinding.status == "active",
                )
            )
            bindings = result.scalars().all()

        assert bindings == []

    async def test_android_login_consumes_authorized_devices_limit(
        self,
        client,
        admin_headers,
        project_id,
    ):
        user = await _create_user_with_authorization(
            client,
            admin_headers,
            project_id,
            authorized_devices=1,
        )

        first_login = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            project_uuid="00000000-0000-0000-0000-000000000001",
            device_id=f"A-{uuid.uuid4().hex[:8]}",
            client_type="android",
        )
        assert first_login.status_code == 200, first_login.text

        second_login = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            project_uuid="00000000-0000-0000-0000-000000000001",
            device_id=f"B-{uuid.uuid4().hex[:8]}",
            client_type="android",
        )
        assert second_login.status_code == 403
        assert "设备绑定数量已达上限" in second_login.json()["detail"]

    async def test_project_a_binding_and_online_does_not_allow_project_b_heartbeat(
        self,
        client,
        admin_headers,
        project_id,
        second_project_id,
    ):
        user = await _create_user_with_authorization(
            client,
            admin_headers,
            project_id,
            authorized_devices=1,
        )
        device_id = f"cross_project_{uuid.uuid4().hex[:10]}"

        login_a = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            project_uuid="00000000-0000-0000-0000-000000000001",
            device_id=device_id,
            client_type="android",
        )
        assert login_a.status_code == 200, login_a.text
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

        heartbeat_a = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(device_id, status="running", game_data={"project": "A"}),
            headers=headers_a,
        )
        assert heartbeat_a.status_code == 200, heartbeat_a.text

        await client.post(
            f"/api/users/{user['user_id']}/authorizations",
            json={
                "game_project_id": second_project_id,
                "user_level": "normal",
                "authorized_devices": 1,
            },
            headers={**admin_headers, "Idempotency-Key": _idem("grant")},
        )

        login_b = await _login_user(
            client,
            username=user["username"],
            password=user["password"],
            project_uuid=SECOND_GAME_PROJECT_UUID,
            device_id=f"PC-B-{uuid.uuid4().hex[:8]}",
            client_type="pc",
        )
        assert login_b.status_code == 200, login_b.text
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

        heartbeat_b = await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(device_id, status="running", game_data={"project": "B"}),
            headers=headers_b,
        )
        assert heartbeat_b.status_code == 403
        assert heartbeat_b.json()["detail"] == "设备未绑定到当前项目，拒绝上报"


class TestDeviceList:
    async def test_device_list_after_heartbeat(self, client, admin_headers, project_id):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(session["device_id"], status="idle", game_data={"level": 50}),
            headers=headers,
        )

        r = await client.get("/api/device/list", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["online_count"] >= 1

        online_devices = [d for d in data["devices"] if d["is_online"]]
        our_device = next((d for d in online_devices if d["device_id"] == session["device_id"]), None)
        assert our_device is not None
        assert our_device["device_id"] == session["device_id"]

    async def test_device_data_after_heartbeat(self, client, admin_headers, project_id):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        await client.post(
            "/api/device/heartbeat",
            json=_heartbeat_payload(session["device_id"], status="running", game_data={"task": "采集", "gold": 9999}),
            headers=headers,
        )

        r = await client.get(f"/api/device/data?device_id={session['device_id']}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["device_id"] == session["device_id"]
        assert data["is_online"] is True
        assert data["source"] == "redis"
        assert data["game_data"]["gold"] == 9999

    async def test_device_api_rejects_old_token_after_authorization_suspended(
        self,
        client,
        admin_headers,
        project_id,
    ):
        session = await _login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        heartbeat_body = _heartbeat_payload(session["device_id"], status="running", game_data={"gold": 777})

        r1 = await client.post("/api/device/heartbeat", json=heartbeat_body, headers=headers)
        assert r1.status_code == 200

        suspend = await client.post(
            f"/api/users/{session['user_id']}/authorizations/{session['authorization_id']}/suspend",
            headers=admin_headers,
        )
        assert suspend.status_code == 200, suspend.text

        r2 = await client.post("/api/device/heartbeat", json=heartbeat_body, headers=headers)
        assert r2.status_code == 403

        r3 = await client.get("/api/device/list", headers=headers)
        assert r3.status_code == 403

        r4 = await client.get(
            f"/api/device/data?device_id={session['device_id']}",
            headers=headers,
        )
        assert r4.status_code == 403

        enable = await client.post(
            f"/api/users/{session['user_id']}/authorizations/{session['authorization_id']}/enable",
            headers=admin_headers,
        )
        assert enable.status_code == 200, enable.text

        r5 = await client.get("/api/device/list", headers=headers)
        assert r5.status_code == 200

        r6 = await client.post("/api/device/heartbeat", json=heartbeat_body, headers=headers)
        assert r6.status_code == 200
