-- ============================================================
-- 文件位置: scripts/setup_game_db.sql
-- 文件名称: setup_game_db.sql
-- 作者: 蜂巢·大圣 (Hive-GreatSage)
-- 日期/时间: 2026-05-02
-- 版本: V1.1.0
-- 功能说明:
--   开发 / 抢修用游戏库权限修复 SQL。
--
--   当前定位:
--     1. 本脚本不是常规项目创建主流程。
--     2. 常规项目创建应走管理后台项目创建接口。
--     3. 本脚本只用于开发期修复历史游戏库权限。
--     4. 本脚本不修改数据库用户密码。
--
--   重要安全边界:
--     1. 不再执行 ALTER ROLE ... WITH PASSWORD。
--     2. 如密码认证失败，应由 DBA / 开发者在受控环境单独处理密码。
--     3. 本脚本只处理 CONNECT、schema、表、序列、默认权限。
--
--   默认变量:
--     hgs_game_db = hive_game_001
--     hgs_db_user = hive_user
--
--   运行方式:
--     psql -U postgres -p 15432 -f scripts/setup_game_db.sql
--
--   指定变量运行:
--     psql -U postgres -p 15432 \
--       -v hgs_game_db=hive_game_001 \
--       -v hgs_db_user=hive_user \
--       -f scripts/setup_game_db.sql
--
--   改进历史:
--     V1.1.0 (2026-05-02) - 移除硬编码重置 hive_user 密码；降级为开发 / 抢修权限修复脚本。
--     V1.0.0 (2026-04-25) - 初始权限修复脚本。
-- ============================================================

\set ON_ERROR_STOP on

\if :{?hgs_game_db}
\else
\set hgs_game_db 'hive_game_001'
\endif

\if :{?hgs_db_user}
\else
\set hgs_db_user 'hive_user'
\endif

\echo '--- HiveGreatSage-Verify 游戏库权限修复开始 ---'
\echo '目标游戏库: ' :hgs_game_db
\echo '目标数据库用户: ' :hgs_db_user
\echo '注意: 本脚本不会修改数据库用户密码。'

-- ------------------------------------------------------------
-- 步骤 1：确保目标用户存在
-- ------------------------------------------------------------
SELECT rolname AS target_role
FROM pg_roles
WHERE rolname = :'hgs_db_user';

-- 如果上一条查询无结果，请先创建数据库用户或修复数据库用户配置。
-- 本脚本不会创建用户，也不会设置密码。

-- ------------------------------------------------------------
-- 步骤 2：确保目标游戏库存在
-- ------------------------------------------------------------
SELECT datname AS target_database
FROM pg_database
WHERE datname = :'hgs_game_db';

-- 如果上一条查询无结果，请先通过管理后台项目创建流程、
-- 或开发抢修脚本 scripts/provision_game_db.py 创建游戏库。

-- ------------------------------------------------------------
-- 步骤 3：授予数据库 CONNECT 权限
-- ------------------------------------------------------------
GRANT CONNECT ON DATABASE :"hgs_game_db" TO :"hgs_db_user";

-- ------------------------------------------------------------
-- 步骤 4：进入目标游戏库
-- ------------------------------------------------------------
\connect :"hgs_game_db"

-- ------------------------------------------------------------
-- 步骤 5：授予 public schema 使用权
-- ------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO :"hgs_db_user";

-- ------------------------------------------------------------
-- 步骤 6：授予现有表和序列权限
-- ------------------------------------------------------------
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"hgs_db_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"hgs_db_user";

-- ------------------------------------------------------------
-- 步骤 7：授予未来表和序列默认权限
-- ------------------------------------------------------------
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO :"hgs_db_user";

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO :"hgs_db_user";

-- ------------------------------------------------------------
-- 步骤 8：验证权限
-- ------------------------------------------------------------
SELECT
    current_database() AS database_name,
    :'hgs_db_user' AS database_user,
    has_database_privilege(:'hgs_db_user', current_database(), 'CONNECT') AS can_connect;

SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

\echo '--- 权限配置完成 ---'
\echo '如仍出现 password authentication failed，请在受控环境单独检查 pg_hba.conf 与数据库用户密码。'