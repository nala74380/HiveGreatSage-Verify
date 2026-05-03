r"""
文件位置: tests/test_update.py
名称: 热更新接口集成测试
作者: 蜂巢·大圣 (HiveGreatSage)
时间: 2026-04-24
版本: V1.0.4
功能说明:
    测试 GET /api/update/check 和 GET /api/update/download 接口。

    V2 迁移后 VersionRecord 已迁至主库，seed_version 写入主库 version_record。
    测试数据写入前后会清理同名测试版本记录和 Redis 热更新缓存，避免残留状态影响断言。

改进历史:
    V1.0.4 (2026-05-03) - 授权测试请求补齐 user_level 与 authorized_devices，匹配 AuthorizationCreateRequest
    V1.0.3 (2026-05-03) - seed_version 增加残留测试记录清理和 Redis 热更新缓存清理
    V1.0.2 (2026-05-03) - seed_version 改用主库 session_factory（D014 V2 迁移）
    V1.0.1 (2026-04-25) - seed_version 改用 conftest.game_session_factory
    V1.0.0 - 初始版本
"""

import uuid

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient
from sqlalchemy import text

from app.config import settings
from tests.conftest import GAME_PROJECT_CODE

# 测试版本数据
TEST_VERSION_PC      = "9.9.9"
TEST_VERSION_ANDROID = "9.9.9"
TEST_PACKAGE_PATH_ANDROID = f"game_001/android/packages/test_v{TEST_VERSION_ANDROID}.lrj"
TEST_PACKAGE_PATH_PC      = f"game_001/pc/packages/test_v{TEST_VERSION_PC}.zip"
TEST_CHECKSUM = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
TEST_RELEASE_NOTES = "测试版本 - 自动化测试"
TEST_LOGIN_SECRET = "UpdateTestSecret2026"
TEST_USER_LEVEL = "normal"
TEST_AUTHORIZED_DEVICES = 20


# ── 辅助 ──────────────────────────────────────────────────────

async def _create_user_and_login(
    client: AsyncClient,
    admin_headers: dict,
    project_id: int,
) -> str:
    """创建用户、授权、登录，返回 access_token。"""
    suffix = uuid.uuid4().hex[:8]
    username = f"upd_test_{suffix}"

    r = await client.post("/api/users/", json={
        "username": username,
        "password": TEST_LOGIN_SECRET,
    }, headers=admin_headers)
    assert r.status_code == 201, f"创建用户失败: {r.text}"
    user_id = r.json()["id"]

    r = await client.post(
        f"/api/users/{user_id}/authorizations",
        json={
            "game_project_id": project_id,
            "user_level": TEST_USER_LEVEL,
            "authorized_devices": TEST_AUTHORIZED_DEVICES,
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, f"授权失败: {r.text}"

    r = await client.post("/api/auth/login", json={
        "username": username,
        "password": TEST_LOGIN_SECRET,
        "project_uuid": "00000000-0000-0000-0000-000000000001",
        "device_fingerprint": f"upd_dev_{uuid.uuid4().hex[:12]}",
        "client_type": "android",
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()["access_token"]


async def _clear_update_cache() -> None:
    """清理热更新测试会命中的 Redis 缓存。"""
    redis = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await redis.delete(
            f"update:latest:{GAME_PROJECT_CODE}:android",
            f"update:latest:{GAME_PROJECT_CODE}:pc",
        )
    finally:
        await redis.aclose()


# ── Fixture：插入测试版本记录 ─────────────────────────────────

@pytest.fixture
async def seed_version(session_factory, project_id):
    """
    将测试版本记录注入主库 version_record（V2 迁移后不再使用游戏库版本表）。
    """
    async with session_factory() as session:
        # 先删除上一次异常中断可能遗留的测试版本，避免唯一索引冲突。
        await session.execute(text(
            "DELETE FROM version_record WHERE release_notes = :notes"
        ), {"notes": TEST_RELEASE_NOTES})

        # 再停用已有活跃版本，保证本 fixture 写入的版本成为当前活跃版本。
        await session.execute(text(
            "UPDATE version_record SET is_active = FALSE "
            "WHERE game_project_id = :pid AND client_type = 'android' AND is_active = TRUE"
        ), {"pid": project_id})
        await session.execute(text(
            "UPDATE version_record SET is_active = FALSE "
            "WHERE game_project_id = :pid AND client_type = 'pc' AND is_active = TRUE"
        ), {"pid": project_id})

        # 插入测试版本。
        await session.execute(text("""
            INSERT INTO version_record
                (game_project_id, client_type, version, package_path, checksum_sha256,
                 release_notes, is_active, force_update)
            VALUES
                (:pid, 'android', :v_a, :p_a, :c, :notes, TRUE, FALSE),
                (:pid, 'pc',      :v_p, :p_p, :c, :notes, TRUE, FALSE)
        """), {
            "pid": project_id,
            "v_a": TEST_VERSION_ANDROID,
            "p_a": TEST_PACKAGE_PATH_ANDROID,
            "v_p": TEST_VERSION_PC,
            "p_p": TEST_PACKAGE_PATH_PC,
            "c": TEST_CHECKSUM,
            "notes": TEST_RELEASE_NOTES,
        })
        await session.commit()

    await _clear_update_cache()

    yield

    # teardown：删除测试版本记录并清理缓存。
    async with session_factory() as session:
        await session.execute(text(
            "DELETE FROM version_record WHERE release_notes = :notes"
        ), {"notes": TEST_RELEASE_NOTES})
        await session.commit()

    await _clear_update_cache()


# ── 测试类：版本检查 ──────────────────────────────────────────

class TestCheckUpdate:
    async def test_check_requires_auth(self, client):
        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": "1.0.0"})
        assert r.status_code == 403

    async def test_check_invalid_version_format(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": "not_a_version"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422

    async def test_check_invalid_client_type(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "ios", "current_version": "1.0.0"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422

    async def test_check_old_version_needs_update(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": "0.0.1"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["need_update"] is True
        assert data["current_version"] == TEST_VERSION_ANDROID
        assert data["client_type"] == "android"
        assert data["game_project_code"] == GAME_PROJECT_CODE
        assert data["force_update"] is False
        assert data["checksum_sha256"] == TEST_CHECKSUM

    async def test_check_same_version_no_update(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": TEST_VERSION_ANDROID},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["need_update"] is False

    async def test_check_newer_version_no_update(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": "99.0.0"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["need_update"] is False

    async def test_check_pc_client(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/check",
                             params={"client_type": "pc", "current_version": "0.0.1"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["need_update"] is True
        assert r.json()["client_type"] == "pc"

    async def test_check_redis_cache(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        headers = {"Authorization": f"Bearer {token}"}
        params  = {"client_type": "android", "current_version": "0.0.1"}

        r1 = await client.get("/api/update/check", params=params, headers=headers)
        r2 = await client.get("/api/update/check", params=params, headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["current_version"] == r2.json()["current_version"]
        assert r1.json()["need_update"] == r2.json()["need_update"]


# ── 测试类：下载链接 ──────────────────────────────────────────

class TestDownloadUpdate:
    async def test_download_requires_auth(self, client):
        r = await client.get("/api/update/download", params={"client_type": "android"})
        assert r.status_code == 403

    async def test_download_android_returns_url(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/download",
                             params={"client_type": "android"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "download_url" in data
        assert "expires_at" in data
        assert data["version"] == TEST_VERSION_ANDROID
        assert data["checksum_sha256"] == TEST_CHECKSUM

    async def test_download_url_contains_token(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/download",
                             params={"client_type": "android"},
                             headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        assert "token=" in data["download_url"] or "hive" in data["download_url"]

    async def test_download_invalid_client_type(
        self, client, admin_headers, project_id, seed_version
    ):
        token = await _create_user_and_login(client, admin_headers, project_id)
        r = await client.get("/api/update/download",
                             params={"client_type": "wearable"},
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422
