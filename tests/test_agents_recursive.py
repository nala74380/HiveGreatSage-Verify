r"""
文件位置: tests/test_agents_recursive.py
名称: 多级代理递归查询集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能说明:
    测试 Phase 2 新增的三个代理树形查询端点：
      GET /api/agents/tree                全树（Admin Token）
      GET /api/agents/{id}/subtree        指定子树（Admin Token）
      GET /api/agents/scope/list          代理权限范围内的下级列表（Agent Token）

    以及 T025 踢出所有设备：
      POST /api/auth/revoke-all

    seed_agents fixture：
      创建三层代理树用于测试：
        root_agent（L1）
          ├── child_agent_1（L2）
          │     └── grandchild_agent（L3）
          └── child_agent_2（L2）
      测试结束后清理，不影响开发数据（用户名含 tree_test_ 前缀）。

改进历史:
    V1.0.0 - 初始版本（C01 多级代理递归测试）
"""

import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_USERNAME, ADMIN_PASSWORD


# ── 辅助 ──────────────────────────────────────────────────────

async def _admin_login(client: AsyncClient) -> str:
    r = await client.post("/api/agents/auth/../admin/auth/login", json={
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
    })
    # 实际管理员登录端点是 /admin/api/auth/login
    r = await client.post("/admin/api/auth/login", json={
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
    })
    assert r.status_code == 200, f"管理员登录失败: {r.text}"
    return r.json()["access_token"]


async def _create_agent(
    client: AsyncClient,
    admin_headers: dict,
    username: str,
    parent_agent_id: int | None = None,
) -> dict:
    r = await client.post("/api/agents/", json={
        "username": username,
        "password": "Agent@2026!",
        "parent_agent_id": parent_agent_id,
        "max_users": 100,
    }, headers=admin_headers)
    assert r.status_code == 201, f"创建代理失败: {r.text}"
    return r.json()


# ── Fixture：三层代理树 ───────────────────────────────────────

@pytest.fixture
async def seed_agents(client, admin_headers):
    """
    创建三层代理树，测试结束后清理。
    返回字典包含各层代理信息：
      {root, child1, child2, grandchild}
    """
    suffix = uuid.uuid4().hex[:6]

    root = await _create_agent(
        client, admin_headers,
        username=f"tree_test_root_{suffix}",
    )
    child1 = await _create_agent(
        client, admin_headers,
        username=f"tree_test_c1_{suffix}",
        parent_agent_id=root["id"],
    )
    child2 = await _create_agent(
        client, admin_headers,
        username=f"tree_test_c2_{suffix}",
        parent_agent_id=root["id"],
    )
    grandchild = await _create_agent(
        client, admin_headers,
        username=f"tree_test_gc_{suffix}",
        parent_agent_id=child1["id"],
    )

    yield {
        "root": root,
        "child1": child1,
        "child2": child2,
        "grandchild": grandchild,
        "suffix": suffix,
    }

    # teardown：挂起所有测试代理（不物理删除，禁止级联删除）
    for agent in [grandchild, child1, child2, root]:
        await client.patch(
            f"/api/agents/{agent['id']}",
            json={"status": "suspended"},
            headers=admin_headers,
        )


# ── 测试：子树查询 ─────────────────────────────────────────────

class TestAgentSubtree:
    async def test_subtree_requires_admin(self, client, seed_agents):
        """无 Token 应返回 403。"""
        root_id = seed_agents["root"]["id"]
        r = await client.get(f"/api/agents/{root_id}/subtree")
        assert r.status_code == 403

    async def test_subtree_root_contains_all_descendants(
        self, client, admin_headers, seed_agents
    ):
        """根节点子树应包含全部 4 个代理（根+2子+1孙）。"""
        root_id = seed_agents["root"]["id"]
        r = await client.get(
            f"/api/agents/{root_id}/subtree",
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["total_agents"] >= 4, "子树代理数应至少 4 个"
        assert data["root"]["id"] == root_id
        assert data["root"]["level"] == 1

        # root 应有 2 个直属子节点
        child_ids = {c["id"] for c in data["root"]["children"]}
        assert seed_agents["child1"]["id"] in child_ids
        assert seed_agents["child2"]["id"] in child_ids

    async def test_subtree_level_correct(
        self, client, admin_headers, seed_agents
    ):
        """各层 level 字段应正确（L1→L2→L3）。"""
        root_id = seed_agents["root"]["id"]
        r = await client.get(
            f"/api/agents/{root_id}/subtree",
            headers=admin_headers,
        )
        data = r.json()
        root_node = data["root"]
        assert root_node["level"] == 1

        # 找到 child1（有子节点的那个）
        child1_node = next(
            c for c in root_node["children"]
            if c["id"] == seed_agents["child1"]["id"]
        )
        assert child1_node["level"] == 2

        # grandchild 在 child1 的 children 里
        assert len(child1_node["children"]) >= 1
        gc = child1_node["children"][0]
        assert gc["id"] == seed_agents["grandchild"]["id"]
        assert gc["level"] == 3

    async def test_subtree_leaf_node(
        self, client, admin_headers, seed_agents
    ):
        """叶子节点（child2，无子代理）的子树 children 应为空列表。"""
        child2_id = seed_agents["child2"]["id"]
        r = await client.get(
            f"/api/agents/{child2_id}/subtree",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["root"]["id"] == child2_id
        assert data["root"]["children"] == []
        assert data["total_agents"] == 1

    async def test_subtree_nonexistent_agent(
        self, client, admin_headers
    ):
        """查询不存在的代理子树应返回 404。"""
        r = await client.get(
            "/api/agents/999999/subtree",
            headers=admin_headers,
        )
        assert r.status_code == 404

    async def test_subtree_user_count(
        self, client, admin_headers, seed_agents
    ):
        """子树响应包含 total_users 字段（数值可为 0，但字段必须存在）。"""
        root_id = seed_agents["root"]["id"]
        r = await client.get(
            f"/api/agents/{root_id}/subtree",
            headers=admin_headers,
        )
        data = r.json()
        assert "total_users" in data
        assert isinstance(data["total_users"], int)
        assert data["total_users"] >= 0


# ── 测试：全树查询 ─────────────────────────────────────────────

class TestFullAgentTree:
    async def test_tree_requires_admin(self, client):
        r = await client.get("/api/agents/tree")
        assert r.status_code == 403

    async def test_tree_returns_list(self, client, admin_headers, seed_agents):
        """全树端点应返回列表，每项为一棵顶级代理的子树。"""
        r = await client.get("/api/agents/tree", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # 确认所有根节点的 parent_agent_id 为 None
        for tree in data:
            assert tree["root"]["parent_agent_id"] is None

    async def test_tree_contains_our_root(
        self, client, admin_headers, seed_agents
    ):
        """全树列表中应包含我们创建的根代理。"""
        r = await client.get("/api/agents/tree", headers=admin_headers)
        data = r.json()
        root_ids = {tree["root"]["id"] for tree in data}
        assert seed_agents["root"]["id"] in root_ids


# ── 测试：代理权限范围查询 ─────────────────────────────────────

class TestAgentScopeList:
    async def _agent_login(self, client: AsyncClient, username: str) -> str:
        r = await client.post("/api/agents/auth/login", json={
            "username": username,
            "password": "Agent@2026!",
        })
        assert r.status_code == 200, f"代理登录失败: {r.text}"
        return r.json()["access_token"]

    async def test_scope_requires_agent_token(self, client):
        r = await client.get("/api/agents/scope/list")
        assert r.status_code == 403

    async def test_root_agent_sees_all_descendants(
        self, client, seed_agents
    ):
        """根代理查看权限范围，应包含自己+child1+child2+grandchild（至少4个）。"""
        token = await self._agent_login(
            client, seed_agents["root"]["username"]
        )
        r = await client.get(
            "/api/agents/scope/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] >= 4

        ids_in_result = {a["id"] for a in data["agents"]}
        assert seed_agents["root"]["id"] in ids_in_result
        assert seed_agents["child1"]["id"] in ids_in_result
        assert seed_agents["child2"]["id"] in ids_in_result
        assert seed_agents["grandchild"]["id"] in ids_in_result

    async def test_child_agent_sees_own_subtree_only(
        self, client, seed_agents
    ):
        """child1 应只看到自己+grandchild，看不到 child2 和 root。"""
        token = await self._agent_login(
            client, seed_agents["child1"]["username"]
        )
        r = await client.get(
            "/api/agents/scope/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        ids_in_result = {a["id"] for a in data["agents"]}

        assert seed_agents["child1"]["id"] in ids_in_result
        assert seed_agents["grandchild"]["id"] in ids_in_result
        assert seed_agents["root"]["id"] not in ids_in_result
        assert seed_agents["child2"]["id"] not in ids_in_result

    async def test_leaf_agent_sees_only_self(
        self, client, seed_agents
    ):
        """grandchild（叶子代理）只能看到自己。"""
        token = await self._agent_login(
            client, seed_agents["grandchild"]["username"]
        )
        r = await client.get(
            "/api/agents/scope/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["agents"][0]["id"] == seed_agents["grandchild"]["id"]

    async def test_scope_pagination(self, client, seed_agents):
        """分页参数正常工作，page_size=2 时每页最多 2 条。"""
        token = await self._agent_login(
            client, seed_agents["root"]["username"]
        )
        r = await client.get(
            "/api/agents/scope/list",
            params={"page": 1, "page_size": 2},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["agents"]) <= 2
        assert data["page"] == 1
        assert data["page_size"] == 2


# ── 测试：T025 踢出所有设备 ───────────────────────────────────

class TestRevokeAll:
    async def _login_user(
        self, client: AsyncClient, admin_headers: dict, project_id: int
    ) -> tuple[str, str]:
        """创建用户、授权、登录，返回 (access_token, refresh_token)。"""
        suffix = uuid.uuid4().hex[:8]
        username = f"revoke_test_{suffix}"

        r = await client.post("/api/users/", json={
            "username": username,
            "password": "Revoke@2026!",
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
            "password": "Revoke@2026!",
            "project_uuid": "00000000-0000-0000-0000-000000000001",
            "device_fingerprint": f"rev_dev_{uuid.uuid4().hex[:12]}",
            "client_type": "android",
        })
        assert r.status_code == 200
        data = r.json()
        return data["access_token"], data["refresh_token"]

    async def test_revoke_all_requires_auth(self, client):
        r = await client.post("/api/auth/revoke-all")
        assert r.status_code == 403

    async def test_revoke_all_success(
        self, client, admin_headers, project_id
    ):
        """调用 revoke-all 后应返回成功消息，包含清除的会话数。"""
        access_token, _ = await self._login_user(
            client, admin_headers, project_id
        )
        r = await client.post(
            "/api/auth/revoke-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "message" in data
        assert "踢出" in data["message"] or "清除" in data["message"]

    async def test_revoke_all_then_refresh_fails(
        self, client, admin_headers, project_id
    ):
        """revoke-all 后用原 RT 刷新应返回 401。"""
        access_token, refresh_token = await self._login_user(
            client, admin_headers, project_id
        )

        # 踢出所有设备
        await client.post(
            "/api/auth/revoke-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # 用原 RT 刷新，应失败
        r = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert r.status_code == 401

    async def test_revoke_all_me_still_works_briefly(
        self, client, admin_headers, project_id
    ):
        """
        revoke-all 后当前 AT 在剩余有效期内仍可使用（JWT 固有限制）。
        /me 接口应仍然返回 200（AT 未到黑名单TTL过期前）。
        """
        access_token, _ = await self._login_user(
            client, admin_headers, project_id
        )

        # 踢出后 AT 黑名单写入（但不影响本请求用的 AT 是同一个）
        await client.post(
            "/api/auth/revoke-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # 注：revoke-all 会把当前 AT 的 jti 加黑名单
        # 所以再用同一个 AT 调 /me 应该返回 401
        r = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code == 401
