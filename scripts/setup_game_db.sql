-- ============================================================
-- 文件位置: scripts/setup_game_db.sql
-- 名称: hive_game_001 数据库权限修复脚本
-- 作者: 蜂巢·大圣 (Hive-GreatSage)
-- 时间: 2026-04-25
-- 说明:
--   解决 asyncpg.exceptions.InvalidPasswordError 问题。
--   根本原因：hive_user 缺少对 hive_game_001 的认证/访问权限，
--   而 hive_platform 正常是因为有独立的 pg_hba 规则或权限配置。
--
--   运行方式（以 postgres 超级用户身份）：
--     psql -U postgres -p 15432 -f scripts/setup_game_db.sql
--   或直接连接后执行：
--     psql -U postgres -p 15432
--     \i scripts/setup_game_db.sql
-- ============================================================

-- 步骤1：重置 hive_user 密码（确保以 scram-sha-256 格式存储）
-- 如果 pg_hba.conf 要求 scram-sha-256 认证，但密码是以 md5 格式存储的，
-- 即使密码正确也会认证失败。重置密码可解决格式不匹配问题。
ALTER ROLE hive_user WITH PASSWORD 'hive_dev_2026';

-- 步骤2：确保 hive_user 有连接 hive_game_001 的权限
GRANT CONNECT ON DATABASE hive_game_001 TO hive_user;

-- 步骤3：进入 hive_game_001 库，授权 schema 和表
\c hive_game_001

-- 授权 schema 使用权
GRANT USAGE ON SCHEMA public TO hive_user;

-- 授权现有所有表的权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hive_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hive_user;

-- 授权未来创建的表也自动有权限（防止 alembic 迁移后权限缺失）
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO hive_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO hive_user;

-- 步骤4（可选）：验证权限是否正确
-- 以下查询应该返回 hive_user 有 CONNECT 权限
SELECT datname, has_database_privilege('hive_user', datname, 'CONNECT') AS can_connect
FROM pg_database
WHERE datname IN ('hive_platform', 'hive_game_001');

\echo '--- 权限配置完成 ---'
\echo '现在可以重新运行测试: python scripts/run_tests.py'
