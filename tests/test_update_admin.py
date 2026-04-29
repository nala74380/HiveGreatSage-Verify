r"""
文件位置: tests/test_update_admin.py
名称: 热更新管理接口集成测试
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.2
功能说明:
    测试 POST /admin/api/updates/{game_project_code}/{client_type}。

    cleanup_test_versions（scope="module"，autouse=True）：
      模块级 teardown，只在模块所有测试结束后运行一次。
      若 hive_game_001 不可访问则跳过 cleanup（不报 ERROR）。
      scope="module" 可依赖 session 级 game_session_factory/game_db_accessible。

    需要游戏库的上传测试（android/pc/force_update 等）：
      若 hive_game_001 不可访问则 pytest.skip。
      不需要游戏库的校验测试（422 响应）不受影响，仍正常运行。

改进历史:
    V1.0.2 (2026-04-25) - cleanup_test_versions 改回 scope=module + 安全降级；
                          上传测试添加 game_db_accessible skip 检查；
                          修复 function-scope autouse 导致校验测试全部 ERROR 的 regression
    V1.0.1 (2026-04-25) - cleanup_test_versions 改用 conftest.game_session_factory
    V1.0.0 - 初始版本
"""

import pytest
from sqlalchemy import text

from tests.conftest import GAME_PROJECT_CODE, GAME_DB_SKIP_MSG

_FAKE_LRJ_CONTENT = b"PK\x03\x04FAKE_LRJ_CONTENT_FOR_TESTING_ONLY"
_FAKE_ZIP_CONTENT = b"PK\x03\x04FAKE_ZIP_CONTENT_FOR_TESTING_ONLY"
_TEST_RELEASE_NOTES = "test_upload"


@pytest.fixture(scope="module", autouse=True)
async def cleanup_test_versions(game_session_factory, game_db_accessible):
    """
    模块级 teardown（scope=module，autouse=True）：
    所有模块测试结束后，清理 release_notes='test_upload' 的版本记录。

    设计说明：
    - scope=module：只在整个模块结束后运行一次 teardown，不影响单个测试结果
    - 依赖 session 级的 game_session_factory 和 game_db_accessible（合法的 scope 组合）
    - game_db_accessible=False 时跳过 cleanup，不报 ERROR
    """
    yield  # 所有测试先运行

    if not game_db_accessible:
        return  # game DB 不可用时静默跳过清理

    try:
        async with game_session_factory() as session:
            await session.execute(
                text("DELETE FROM version_record WHERE release_notes = :notes"),
                {"notes": _TEST_RELEASE_NOTES},
            )
            await session.commit()
    except Exception as e:
        import warnings
        warnings.warn(f"cleanup_test_versions teardown failed: {e}")


class TestUploadVersion:
    # ── 不需要游戏库的校验测试（始终运行）─────────────────────

    async def test_upload_requires_admin_token(self, client):
        """无 Token 应返回 403。"""
        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data={"version": "9.1.0", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
        )
        assert r.status_code == 403

    async def test_upload_invalid_client_type(self, client, admin_headers):
        """非法 client_type 应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/ios",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_invalid_version_format(self, client, admin_headers):
        """非法版本号格式应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data={"version": "not_a_version", "force_update": "false"},
            files={"file": ("test.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_invalid_file_extension(self, client, admin_headers):
        """不支持的文件格式应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("malware.exe", b"fake", "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_upload_empty_file(self, client, admin_headers):
        """空文件应返回 422。"""
        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data={"version": "1.0.0", "force_update": "false"},
            files={"file": ("empty.lrj", b"", "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 422

    # ── 需要游戏库的上传测试（game DB 不可用时 skip）──────────

    async def test_upload_android_success(
        self, client, admin_headers, game_db_accessible
    ):
        """上传安卓包，应返回 201 并含版本信息。"""
        if not game_db_accessible:
            pytest.skip(GAME_DB_SKIP_MSG)

        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
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
        self, client, admin_headers, game_db_accessible
    ):
        """上传 PC 包，应返回 201。"""
        if not game_db_accessible:
            pytest.skip(GAME_DB_SKIP_MSG)

        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/pc",
            data={"version": "9.1.1", "force_update": "false",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.1.1.zip", _FAKE_ZIP_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["client_type"] == "pc"

    async def test_upload_force_update(
        self, client, admin_headers, game_db_accessible
    ):
        """force_update=true 时响应中应为 True。"""
        if not game_db_accessible:
            pytest.skip(GAME_DB_SKIP_MSG)

        r = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data={"version": "9.2.0", "force_update": "true",
                  "release_notes": _TEST_RELEASE_NOTES},
            files={"file": ("v9.2.0.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["force_update"] is True

    async def test_upload_idempotent_same_version(
        self, client, admin_headers, game_db_accessible
    ):
        """同版本重复上传应返回 201（覆盖旧包，checksum 不同）。"""
        if not game_db_accessible:
            pytest.skip(GAME_DB_SKIP_MSG)

        payload = {"version": "9.3.0", "force_update": "false",
                   "release_notes": _TEST_RELEASE_NOTES}
        r1 = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
            data=payload,
            files={"file": ("v9.3.0.lrj", _FAKE_LRJ_CONTENT, "application/octet-stream")},
            headers=admin_headers,
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
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
            "username": username, "password": "Test@2026!", "user_level": "tester",
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
            f"/admin/api/updates/{GAME_PROJECT_CODE}/android",
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
