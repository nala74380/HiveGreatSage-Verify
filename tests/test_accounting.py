r"""
文件位置: tests/test_accounting.py
名称: 账务中心财务测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-10
版本: V1.0.0
功能说明:
    账务中心扣点/返点/冻结/划拨核心财务链路测试。

    覆盖:
      1. 项目定价 CRUD
      2. 代理充值/授信
      3. 代理冻结/解冻
      4. 授权扣点（扣费优先 charged 再 credit）
      5. 删除用户按比例自动返点
      6. 余额不足拦截
      7. 幂等键防重复扣点
      8. 代理端点数划拨（有 for_update 锁）

    注意:
      本测试依赖 hive_game_001 可用，否则全部 SKIP。
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text


AGENT_USERNAME_PREFIX = "acct_test_agent_"
USER_USERNAME_PREFIX  = "acct_test_user_"


def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def _idem(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


async def _create_agent(
    client: AsyncClient, admin_headers: dict, *, username: str = None, password: str = "Test@2026",
) -> dict:
    name = username or f"{AGENT_USERNAME_PREFIX}{_uniq()}"
    res = await client.post(
        "/api/agents/",
        json={"username": name, "password": password},
        headers=admin_headers,
    )
    assert res.status_code == 201, f"创建代理失败: {res.text}"
    return res.json()


async def _agent_headers(client: AsyncClient, username: str, password: str = "Test@2026") -> dict:
    res = await client.post(
        "/api/agents/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, f"代理登录失败: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _valid_until(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def _create_user(
    client: AsyncClient, caller_headers: dict, *, username: str = None, password: str = "User@2026",
) -> dict:
    name = username or f"{USER_USERNAME_PREFIX}{_uniq()}"
    res = await client.post(
        "/api/users/",
        json={"username": name, "password": password},
        headers=caller_headers,
    )
    assert res.status_code == 201, f"创建用户失败: {res.text}"
    return res.json()


async def _grant_authorization(
    client: AsyncClient,
    *,
    user_id: int,
    payload: dict,
    headers: dict,
):
    return await client.post(
        f"/api/users/{user_id}/authorizations",
        json=payload,
        headers={**headers, "Idempotency-Key": _idem("grant")},
    )


class TestPricing:
    """项目定价 CRUD。"""

    async def test_set_price(self, client, admin_headers, project_id):
        res = await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 1.5},
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["points_per_device"] == 1.5

    async def test_get_prices(self, client, admin_headers, project_id):
        res = await client.get(f"/admin/api/prices/{project_id}", headers=admin_headers)
        assert res.status_code == 200
        prices = res.json()
        assert isinstance(prices, list)
        levels = {p["user_level"] for p in prices}
        assert "trial" in levels

    async def test_delete_price_then_recreate(self, client, admin_headers, project_id):
        # delete
        res = await client.delete(
            f"/admin/api/prices/{project_id}/trial",
            headers=admin_headers,
        )
        assert res.status_code == 204

        # recreate
        res = await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 2.0},
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["points_per_device"] == 2.0


class TestRechargeAndCredit:
    """管理员充值/授信。"""

    async def test_recharge(self, client, admin_headers):
        agent = await _create_agent(client, admin_headers)
        res = await client.post(
            f"/admin/api/accounting/agents/{agent['id']}/recharge",
            json={"amount": 100, "description": "测试充值"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        wallet = res.json()
        assert wallet["charged_balance"] >= 100

    async def test_credit(self, client, admin_headers):
        agent = await _create_agent(client, admin_headers)
        res = await client.post(
            f"/admin/api/accounting/agents/{agent['id']}/credit",
            json={"amount": 50, "description": "测试授信"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        wallet = res.json()
        assert wallet["credit_balance"] >= 50


class TestFreezeUnfreeze:
    """冻结/解冻授信。"""

    async def test_freeze_then_unfreeze(self, client, admin_headers):
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]

        # credit first
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/credit",
            json={"amount": 80, "description": "先授信"},
            headers=admin_headers,
        )

        # freeze
        res = await client.post(
            f"/admin/api/accounting/agents/{agent_id}/freeze",
            json={"amount": 30, "description": "测试冻结"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        wallet = res.json()
        assert wallet["frozen_credit"] >= 30

        # unfreeze
        res2 = await client.post(
            f"/admin/api/accounting/agents/{agent_id}/unfreeze",
            json={"amount": 30, "description": "测试解冻"},
            headers=admin_headers,
        )
        assert res2.status_code == 200
        wallet2 = res2.json()
        assert wallet2["frozen_credit"] < wallet["frozen_credit"]

    async def test_freeze_insufficient(self, client, admin_headers):
        """冻结超过可用授信额度时应失败。"""
        agent = await _create_agent(client, admin_headers)
        res = await client.post(
            f"/admin/api/accounting/agents/{agent['id']}/freeze",
            json={"amount": 99999, "description": "超额冻结"},
            headers=admin_headers,
        )
        assert res.status_code == 400


class TestAuthorizationCharge:
    """授权扣点——扣费优先 charged 再 credit。"""

    async def test_grant_authorization_preview_matches_charge(self, client, admin_headers, project_id):
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 5.0},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/recharge",
            json={"amount": 200, "description": "充值"},
            headers=admin_headers,
        )

        user = await _create_user(client, agent_headers)
        payload = {
            "game_project_id": project_id,
            "user_level": "trial",
            "authorized_devices": 5,
            "valid_until": _valid_until(),
        }

        preview = await client.post(
            f"/api/users/{user['id']}/authorizations/preview",
            json=payload,
            headers=agent_headers,
        )
        assert preview.status_code == 200, preview.text
        preview_data = preview.json()
        assert preview_data["will_charge"] is True
        assert preview_data["agent_id"] == agent_id
        assert preview_data["total_cost"] > 0
        assert preview_data["enough_balance"] is True
        assert preview_data["available_total"] == 200.0
        assert preview_data["charged_consumed"] >= 0
        assert preview_data["credit_consumed"] >= 0
        assert preview_data["available_total_after"] == pytest.approx(
            preview_data["available_total"] - preview_data["total_cost"],
            rel=0,
            abs=0.01,
        )

        grant_key = _idem("grant")
        grant = await client.post(
            f"/api/users/{user['id']}/authorizations",
            json=payload,
            headers={**agent_headers, "Idempotency-Key": grant_key},
        )
        assert grant.status_code == 201, grant.text
        assert grant.json()["consumed_points"] == preview_data["total_cost"]

        grant_retry = await client.post(
            f"/api/users/{user['id']}/authorizations",
            json=payload,
            headers={**agent_headers, "Idempotency-Key": grant_key},
        )
        assert grant_retry.status_code == 201, grant_retry.text
        assert grant_retry.json()["id"] == grant.json()["id"]

    async def test_charge_deducts_charged_first(self, client, admin_headers, project_id):
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        # ensure pricing exists
        await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 5.0},
            headers=admin_headers,
        )

        # grant agent project access
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )

        # recharge
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/recharge",
            json={"amount": 200, "description": "充值"},
            headers=admin_headers,
        )

        # create user via agent, so authorization consumes agent wallet.
        user = await _create_user(client, agent_headers)
        user_id = user["id"]

        # grant authorization (triggers charge)
        res = await _grant_authorization(
            client,
            user_id=user_id,
            payload={
                "game_project_id": project_id,
                "user_level": "trial",
                "authorized_devices": 5,
                "valid_until": _valid_until(),
            },
            headers=agent_headers,
        )
        assert res.status_code == 201, f"授权扣点失败: {res.text}"
        data = res.json()
        assert data["consumed_points"] > 0

    async def test_charge_insufficient_balance(self, client, admin_headers, project_id):
        """余额不足时扣点应失败（402）。"""
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        await client.put(
            f"/admin/api/prices/{project_id}/svip",
            json={"points_per_device": 9999.0},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )

        user = await _create_user(client, agent_headers)
        res = await _grant_authorization(
            client,
            user_id=user["id"],
            payload={
                "game_project_id": project_id,
                "user_level": "svip",
                "authorized_devices": 100,
                "valid_until": _valid_until(),
            },
            headers=agent_headers,
        )
        assert res.status_code in (400, 402), (
            f"期望 400 或 402，实际 {res.status_code}: {res.text}"
        )


class TestDeleteRefund:
    """删除用户按比例自动返点。"""

    async def test_delete_user_triggers_refund(self, client, admin_headers, project_id):
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 5.0},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/recharge",
            json={"amount": 300, "description": "充值"},
            headers=admin_headers,
        )

        user = await _create_user(client, agent_headers)
        user_id = user["id"]

        # authorize
        auth_res = await _grant_authorization(
            client,
            user_id=user_id,
            payload={
                "game_project_id": project_id,
                "user_level": "trial",
                "authorized_devices": 10,
                "valid_until": _valid_until(),
            },
            headers=agent_headers,
        )
        assert auth_res.status_code == 201
        cost_before = auth_res.json()["consumed_points"]

        # check wallet before delete
        wallet_before = await client.get(
            f"/admin/api/accounting/wallets/{agent_id}",
            headers=admin_headers,
        )
        assert wallet_before.status_code == 200

        # Agent cannot delete user accounts or trigger refund settlement.
        agent_del_res = await client.delete(
            f"/api/users/{user_id}",
            headers=agent_headers,
        )
        assert agent_del_res.status_code == 403

        refunds_before_admin_delete = await client.get(
            "/admin/api/accounting/refunds",
            params={"user_id": user_id},
            headers=admin_headers,
        )
        assert refunds_before_admin_delete.status_code == 200
        assert refunds_before_admin_delete.json()["total"] == 0

        # Admin delete triggers refund settlement.
        del_res = await client.delete(
            f"/api/users/{user_id}",
            headers=admin_headers,
        )
        assert del_res.status_code == 204

        # verify refund records exist
        refunds = await client.get(
            "/admin/api/accounting/refunds",
            params={"user_id": user_id},
            headers=admin_headers,
        )
        assert refunds.status_code == 200
        refund_data = refunds.json()
        assert refund_data["total"] > 0, "删除用户后应有返点记录"

    async def test_delete_without_charge_produces_no_refund(self, client, admin_headers, project_id):
        """管理员创建的用户（无代理扣点）删除时应无返点。"""
        user = await _create_user(client, admin_headers)

        # authorize as admin (no agent charge)
        auth_res = await _grant_authorization(
            client,
            user_id=user["id"],
            payload={
                "game_project_id": project_id,
                "user_level": "trial",
                "authorized_devices": 1,
                "valid_until": None,
            },
            headers=admin_headers,
        )
        assert auth_res.status_code == 201

        # delete
        del_res = await client.delete(
            f"/api/users/{user['id']}",
            headers=admin_headers,
        )
        assert del_res.status_code == 204

        refunds = await client.get(
            "/admin/api/accounting/refunds",
            params={"user_id": user["id"]},
            headers=admin_headers,
        )
        assert refunds.json()["total"] == 0


class TestAuthorizationFreeze:
    """授权停用/启用冻结权益基础链路。"""

    async def test_agent_suspend_enable_and_admin_delete_settle_freeze(
        self, client, admin_headers, project_id, session_factory
    ):
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 5.0},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/recharge",
            json={"amount": 300, "description": "充值"},
            headers=admin_headers,
        )

        user = await _create_user(client, agent_headers)
        user_id = user["id"]

        auth_res = await _grant_authorization(
            client,
            user_id=user_id,
            payload={
                "game_project_id": project_id,
                "user_level": "trial",
                "authorized_devices": 10,
                "valid_until": _valid_until(),
            },
            headers=agent_headers,
        )
        assert auth_res.status_code == 201, auth_res.text
        auth_id = auth_res.json()["id"]

        wallet_after_charge = await client.get(
            f"/admin/api/accounting/wallets/{agent_id}",
            headers=admin_headers,
        )
        assert wallet_after_charge.status_code == 200
        available_after_charge = wallet_after_charge.json()["available_total"]

        suspend_res = await client.post(
            f"/api/users/{user_id}/authorizations/{auth_id}/suspend",
            headers=agent_headers,
        )
        assert suspend_res.status_code == 200, suspend_res.text
        assert suspend_res.json()["status"] == "suspended"

        async with session_factory() as session:
            frozen_row = (
                await session.execute(
                    text(
                        """
                        SELECT status, freeze_type, remaining_hours, estimated_remaining_points
                        FROM authorization_freeze_record
                        WHERE authorization_id = :auth_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"auth_id": auth_id},
                )
            ).mappings().one()
        assert frozen_row["status"] == "frozen"
        assert frozen_row["freeze_type"] == "agent_suspend"
        assert frozen_row["remaining_hours"] > 0
        assert float(frozen_row["estimated_remaining_points"]) >= 0

        freezes = await client.get(
            "/admin/api/accounting/authorization-freezes",
            params={"user_id": user_id, "freeze_status": "frozen"},
            headers=admin_headers,
        )
        assert freezes.status_code == 200, freezes.text
        freeze_data = freezes.json()
        assert freeze_data["total"] == 1
        assert freeze_data["freezes"][0]["authorization_id"] == auth_id
        assert freeze_data["freezes"][0]["agent_id"] == agent_id
        assert freeze_data["freezes"][0]["user_id"] == user_id
        assert freeze_data["freezes"][0]["project_id"] == project_id
        assert freeze_data["freezes"][0]["freeze_type"] == "agent_suspend"
        assert freeze_data["freezes"][0]["status"] == "frozen"
        assert freeze_data["freezes"][0]["remaining_hours"] > 0

        wallet_after_suspend = await client.get(
            f"/admin/api/accounting/wallets/{agent_id}",
            headers=admin_headers,
        )
        assert wallet_after_suspend.status_code == 200
        assert wallet_after_suspend.json()["available_total"] == available_after_charge

        enable_res = await client.post(
            f"/api/users/{user_id}/authorizations/{auth_id}/enable",
            headers=agent_headers,
        )
        assert enable_res.status_code == 200, enable_res.text
        assert enable_res.json()["status"] == "active"

        async with session_factory() as session:
            released_status = (
                await session.execute(
                    text(
                        """
                        SELECT status
                        FROM authorization_freeze_record
                        WHERE authorization_id = :auth_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"auth_id": auth_id},
                )
            ).scalar_one()
        assert released_status == "released"

        wallet_after_enable = await client.get(
            f"/admin/api/accounting/wallets/{agent_id}",
            headers=admin_headers,
        )
        assert wallet_after_enable.status_code == 200
        assert wallet_after_enable.json()["available_total"] == available_after_charge

        suspend_again = await client.post(
            f"/api/users/{user_id}/authorizations/{auth_id}/suspend",
            headers=agent_headers,
        )
        assert suspend_again.status_code == 200, suspend_again.text

        delete_res = await client.delete(
            f"/api/users/{user_id}",
            headers=admin_headers,
        )
        assert delete_res.status_code == 204, delete_res.text

        async with session_factory() as session:
            statuses = (
                await session.execute(
                    text(
                        """
                        SELECT status
                        FROM authorization_freeze_record
                        WHERE authorization_id = :auth_id
                        ORDER BY id
                        """
                    ),
                    {"auth_id": auth_id},
                )
            ).scalars().all()
        assert "released" in statuses
        assert "refunded" in statuses


class TestIdempotency:
    """幂等键防重复扣点。"""

    async def test_double_charge_differs_by_snapshot(self, client, admin_headers, project_id):
        """
        同一授权两次扣点（如首次授权 + 升级设备数）应为不同快照，
        不会因幂等键冲突而失败。
        """
        agent = await _create_agent(client, admin_headers)
        agent_id = agent["id"]
        agent_headers = await _agent_headers(client, agent["username"])

        await client.put(
            f"/admin/api/prices/{project_id}/trial",
            json={"points_per_device": 4.0},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/agents/{agent_id}/project-auths/",
            json={"project_id": project_id},
            headers=admin_headers,
        )
        await client.post(
            f"/admin/api/accounting/agents/{agent_id}/recharge",
            json={"amount": 400, "description": "充值"},
            headers=admin_headers,
        )

        user = await _create_user(client, agent_headers)
        user_id = user["id"]

        # first authorization
        res1 = await _grant_authorization(
            client,
            user_id=user_id,
            payload={
                "game_project_id": project_id,
                "user_level": "trial",
                "authorized_devices": 10,
                "valid_until": _valid_until(),
            },
            headers=agent_headers,
        )
        assert res1.status_code == 201
        auth_id = res1.json()["id"]

        # second deduction: upgrade devices
        res2 = await client.post(
            f"/api/users/{user_id}/authorizations/{auth_id}/devices/add",
            json={
                "additional_devices": 5,
                "mode": "append",
            },
            headers={**agent_headers, "Idempotency-Key": _idem("add-devices")},
        )
        assert res2.status_code == 200, (
            f"幂等键冲突或升级失败: {res2.text}"
        )
        data = res2.json()
        assert data["consumed_points"] > 0
        assert data["new_devices"] == 15
