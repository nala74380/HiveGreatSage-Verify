r"""
文件位置: tests/test_update_admin.py
名称: 热更新管理接口集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.1.2
功能说明:
    测试 POST /admin/api/updates/{project_id}/{client_type}。
    V2 迁移后上传已改为主库，路径参数从 code_name 改为 project_id。
    上传、覆盖、缓存失效等管理端测试不依赖游戏库连接。

改进历史:
    V1.1.2 (2026-05-03): 移除同版本重复上传测试中不必要的游戏库可用性跳过条件
    V1.1.1 (2026-05-03): 修复 project_id、game_db_accessible、GAME_DB_SKIP_MSG 测试依赖声明不完整的问题
    V1.1.0 (2026-05-03): 上传路径改用 project_id（D014 V2 迁移）；
                          cleanup 改用主库 session_factory
    V1.0.2 (2026-04-25) - cleanup_test_versions 改回 scope=module
    V1.0.0 - 初始版本
"""

import pytest
from sqlalchemy import text

from tests.conftest import GAME_DB_SKIP_MSG, GAME_PROJECT_CODE

_FAKE_LRJ_CONTENT = b"PK\x03\x04FAKE_LRJ_CONTENT_FOR_TESTING_ONLY"
_FAKE_ZIP_CONTENT = b"PK\x03\x04FAKE_ZIP_CONTENT_FOR_TESTING_ONLY"
_TEST_RELEASE_NOTES = "test_upload"


@pytest.fixture(scope="module", autouse=True)
async def cleanup_test_versions(session_factory):
    """
    模块级 teardown：清理主库 version_record 中的测试版本（V2 迁移后不再使用游戏库）。
    """
    yield

    try:
        async with session_factory() as session:
            await session.execute(
                text("DELETE FROM version_record WHERE release_notes = :notes"),
                {"notes": _TEST_RELEASE_NOTES},
            )
            await session.commit()
    except Exception as e:
        import warnings
        warnings.warn(f"cleanup_test_versions teardown failed: {e}")


class TestUploadVersion:
    # ── 管理端参数/权限校验测试 ────────────────────────────────

    async def test_upload_requires_admin_token(self, client, project_id):
        """无 Token 应返回 403。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "9.1.0", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
        )
        assert r.status_code == 403

    async def test_upload_invalid_client_type(self, client, admin_headers, project_id):
        """非法 client_type 应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/ios",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_invalid_version_format(self, client, admin_headers, project_id):
        """非法版本号格式应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "not_a_version", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_invalid_file_extension(self, client, admin_headers, project_id):
        """不支持的文件格式应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("malware.exe", b"fake", "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_empty_file(self, client, admin_headers, project_id):
        """空文件应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("empty.lrj", b"", "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    # ── 管理端发布/覆盖/缓存失效测试 ──────────────────────────

    async def test_upload_android_success(
        self, client, admin_headers, project_id
    ):
        """上传安卓包，应返回 201 并含版本信息。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "9.1.1", "force_update": "false",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.1.1.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["version"] == "9.1.1"
        assert data["client_type"] == "android"
        assert data["game_project_code"] == GAME_PROJECT_CODE
        assert len(data["checksum_sha256"]) == 64
        assert data["force_update"] is False
        assert GAME_PROJECT_CODE in data["package_path"]

    async def test_upload_pc_success(
        self, client, admin_headers, project_id
    ):
        """上传 PC 包，应返回 201。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/pc",
            data={"version": "9.1.1", "force_update": "false",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.1.1.zip", _FAKE_ZIP_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["client_type"] == "pc"

    async def test_upload_force_update(
        self, client, admin_headers, project_id
    ):
        """force_update=true 时响应中应为 True。"""
        r = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "9.2.0", "force_update": "true",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.2.0.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["force_update"] is True

    async def test_upload_idempotent_same_version(
        self, client, admin_headers, project_id
    ):
        """同版本重复上传应返回 201（覆盖旧包，checksum 不同）。"""
        payload = {"version": "9.3.0", "force_update": "false",
                   "release_notes": _TEST_RELEASE_NOTES}
        r1 = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data=payload,
            files={"file": ("v9.3.0.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/admin/api/updates/{project_id}/android",
            data=payload,
            files={"file": ("v9.3.0.lrj", b"UPDATED_CONTENT", "application/octet-stream")},
            headers=admin_headers,
        )
        assert r2.status_code == 201
        assert r1.json()["checksum_sha256"] != r2.json()["checksum_sha256"]

    async def test_upload_invalidates_redis_cache(
        self, client, admin_headers, project_id, game_db_accessible
    ):
        """上传新版本后 check_update 应立即返回新版本（缓存已失效）。"""
        if not game_db_accessible:
            pytest.skip(GAME_DB_SKIP_MSG)

        import uuid as _uuid
        from tests.conftest import GAME_PROJECT_UUID

        suffix = _uuid.uuid4().hex[:8]
        username = f"upd_adm_test_{suffix}"
        r = await client.post("/api/users/", json={
            "username": username, "password": "Test@2026!",
        }, headers=admin_headers)
        assert r.status_code == 201
        user_id = r.json()["id"]

        await client.post(f"/api/users/{user_id}/authorizations",
                          json={"game_project_id": project_id}, headers=admin_headers)

        r = await client.post("/api/auth/login", json={
            "username": username, "password": "Test@2026!",
            "project_uuid": GAME_PROJECT_UUID,
            "device_fingerprint": f"adm_dev_{_uuid.uuid4().hex[:12]}",
            "client_type": "android",
        })
        assert r.status_code == 200
        user_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        await client.post(
            f"/admin/api/updates/{project_id}/android",
            data={"version": "9.4.0", "force_update": "false",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.4.0.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )

        r = await client.get("/api/update/check",
                             params={"client_type": "android", "current_version": "0.0.1"},
                             headers=user_headers)
        assert r.status_code == 200, r.text
        assert r.json()["need_update"] is True
        assert r.json()["current_version"] == "9.4.0"
