r"""
文件位置: tests/test_params.py
名称: 脚本参数接口集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-24
版本: V1.0.3
功能说明:
    测试 GET /api/params/get 和 POST /api/params/set 接口。

    seed_params fixture：
      使用 conftest.game_session_factory（SQLAlchemy，session 级，SelectorEventLoop）
      操作游戏库，完全替代原先的裸 asyncpg.connect()，根本解决 InvalidPasswordError。
      参数键名均以 "test_" 开头，测试结束后清理，不污染开发数据。

改进历史:
    V1.0.3 (2026-04-25) - seed_params 改用 conftest.game_session_factory，不再使用裸 asyncpg
    V1.0.2 - seed_params 改用原生 asyncpg（已废弃，仍有 ProactorEventLoop 问题）
    V1.0.1 - 改用 conftest.game_session_factory（早期尝试，失败）
    V1.0.0 - 初始版本
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import GAME_PROJECT_CODE, GAME_DB_SKIP_MSG


# ── 辅助：创建用户并登录 ──────────────────────────────────────

async def _create_user_and_login(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
) -> str:
    """创建测试用户、授权、登录，返回 access_token。"""
    suffix = uuid.uuid4().hex[:8]
    username = f"param_test_{suffix}"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": "Param@2026!",
        "user_level": "tester",
    }, headers=admin_headers)
    assert r.status_code == 201, f"创建用户失败: {r.text}"
    user_id = r.json()["id"]

    r = await client.post(f"/api/users/{user_id}/authorizations",
                          json={"game_project_id": project_id},
                          headers=admin_headers)
    assert r.status_code == 201, f"授权失败: {r.text}"

    r = await client.post("/api/auth/login", json={
        "username": username,
        "password": "Param@2026!",
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_fingerprint": f"param_dev_{uuid.uuid4().hex[:12]}",
        "client_type": "android",
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()["access_token"]


# ── Fixture：初始化参数定义 ───────────────────────────────────

@pytest.fixture
async def seed_params(game_session_factory, game_db_accessible):
    """
    将测试参数定义注入游戏库。
    若 hive_game_001 不可访问，pytest.skip 而非 ERROR。
    """
    if not game_db_accessible:
        pytest.skip(GAME_DB_SKIP_MSG)
    async with game_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM script_param_def WHERE param_key LIKE 'test_%'")
        )
        if result.scalar_one() == 0:
            await session.execute(text("""
                INSERT INTO script_param_def
                    (param_key, param_type, default_value, display_name, sort_order)
                VALUES
                    ('test_int_param',    'int',    '10',    '整数参数',   1),
                    ('test_float_param',  'float',  '1.5',   '浮点参数',   2),
                    ('test_bool_param',   'bool',   'true',  '布尔参数',   3),
                    ('test_string_param', 'string', 'hello', '字符串参数', 4),
                    ('test_enum_param',   'enum',   '1',     '枚举参数',   5)
                ON CONFLICT (param_key) DO NOTHING
            """))
            await session.execute(text("""
                UPDATE script_param_def
                SET options = '[{"value": "1", "label": "选项A"}, {"value": "2", "label": "选项B"}]'::jsonb
                WHERE param_key = 'test_enum_param'
            """))
            await session.commit()

    yield

    # teardown：清理测试参数定义和用户参数值
    async with game_session_factory() as session:
        await session.execute(
            text("DELETE FROM user_script_param WHERE param_key LIKE 'test_%'")
        )
        await session.execute(
            text("DELETE FROM script_param_def WHERE param_key LIKE 'test_%'")
        )
        await session.commit()


# ── 测试类 ────────────────────────────────────────────────────

class TestGetParams:
    async def test_get_params_returns_all_with_defaults(
        self, client, admin_headers, project_id, seed_params
    ):
        """未设置任何参数时，GET 返回全部参数且全部使用默认值。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/params/get",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["game_project_code"] == GAME_PROJECT_CODE
        assert data["total"] >= 5

        params_map = {p["param_key"]: p for p in data["params"]}
        assert "test_int_param" in params_map
        p = params_map["test_int_param"]
        assert p["value"] == "10"
        assert p["is_default"] is True
        assert p["param_type"] == "int"

    async def test_get_params_requires_auth(self, client):
        """无 Token 应返回 403。"""
        r = await client.get("/api/params/get")
        assert r.status_code == 403

    async def test_get_params_enum_has_options(
        self, client, admin_headers, project_id, seed_params
    ):
        """enum 类型参数应包含 options 字段。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/params/get",
                             headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        params_map = {p["param_key"]: p for p in data["params"]}
        enum_param = params_map.get("test_enum_param")
        assert enum_param is not None
        assert enum_param["options"] is not None
        assert len(enum_param["options"]) == 2


class TestSetParams:
    async def test_set_int_param(
        self, client, admin_headers, project_id, seed_params
    ):
        """设置 int 参数后，GET 应返回新值且 is_default=False。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [{"param_key": "test_int_param", "param_value": "99"}]
        }, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["updated_count"] == 1
        assert data["failed_count"] == 0

        r2 = await client.get("/api/params/get", headers=headers)
        params_map = {p["param_key"]: p for p in r2.json()["params"]}
        assert params_map["test_int_param"]["value"] == "99"
        assert params_map["test_int_param"]["is_default"] is False

    async def test_set_multiple_params(
        self, client, admin_headers, project_id, seed_params
    ):
        """一次设置多个参数，全部成功。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [
                {"param_key": "test_int_param",    "param_value": "42"},
                {"param_key": "test_bool_param",   "param_value": "false"},
                {"param_key": "test_string_param", "param_value": "南境"},
            ]
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["updated_count"] == 3
        assert data["failed_count"] == 0

    async def test_set_invalid_int_fails(
        self, client, admin_headers, project_id, seed_params
    ):
        """传入非法 int 值应返回部分失败。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [{"param_key": "test_int_param", "param_value": "not_a_number"}]
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["failed_count"] == 1
        assert data["results"][0]["success"] is False
        assert "类型错误" in data["results"][0]["error"]

    async def test_set_invalid_bool_fails(
        self, client, admin_headers, project_id, seed_params
    ):
        """传入非法 bool 值应失败。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [{"param_key": "test_bool_param", "param_value": "yes"}]
        }, headers=headers)
        data = r.json()
        assert data["failed_count"] == 1
        assert "bool" in data["results"][0]["error"]

    async def test_set_nonexistent_key_fails(
        self, client, admin_headers, project_id, seed_params
    ):
        """设置不存在的参数键名应失败。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [{"param_key": "nonexistent_key", "param_value": "123"}]
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["failed_count"] == 1
        assert "不存在" in data["results"][0]["error"]

    async def test_set_partial_success(
        self, client, admin_headers, project_id, seed_params
    ):
        """一合法一非法，应部分成功。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/params/set", json={
            "params": [
                {"param_key": "test_int_param",  "param_value": "77"},
                {"param_key": "test_bool_param", "param_value": "maybe"},
            ]
        }, headers=headers)
        data = r.json()
        assert data["updated_count"] == 1
        assert data["failed_count"] == 1

    async def test_set_upsert_overwrites(
        self, client, admin_headers, project_id, seed_params
    ):
        """同一参数连续设置两次，第二次应覆盖第一次（UPSERT 语义）。"""
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/params/set", json={
            "params": [{"param_key": "test_int_param", "param_value": "100"}]
        }, headers=headers)
        await client.post("/api/params/set", json={
            "params": [{"param_key": "test_int_param", "param_value": "200"}]
        }, headers=headers)

        r = await client.get("/api/params/get", headers=headers)
        params_map = {p["param_key"]: p for p in r.json()["params"]}
        assert params_map["test_int_param"]["value"] == "200"

    async def test_set_requires_auth(self, client):
        """无 Token 应返回 403。"""
        r = await client.post("/api/params/set", json={
            "params": [{"param_key": "test_int_param", "param_value": "1"}]
        })
        assert r.status_code == 403
