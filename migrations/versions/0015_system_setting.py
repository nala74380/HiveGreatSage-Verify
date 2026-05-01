r"""
文件位置: migrations/versions/0015_system_setting.py
文件名称: 0015_system_setting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-04-30
版本: V1.0.0
功能说明:
    新增系统设置表 system_setting。

设计目标:
    将系统设置从前端占位升级为可持久化的平台配置中心。

当前重点:
    - D 模式：公网中转 / 隧道模式 relay_tunnel 作为默认主部署模式。
    - 支持前台修改网络设置。
    - 支持后续 PC 中控 / 安卓脚本拉取客户端网络配置。

说明:
    system_setting 是通用配置表。
    本迁移只落地表结构和网络设置默认值。
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_system_setting"
down_revision = "0014_accounting_center_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_setting",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("setting_key", sa.String(128), nullable=False),
        sa.Column("setting_value", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(32), nullable=False, server_default="string"),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by_admin_id", sa.Integer(), sa.ForeignKey("admin.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("category", "setting_key", name="uq_system_setting_category_key"),
        sa.CheckConstraint(
            "value_type IN ('string', 'int', 'float', 'bool', 'json')",
            name="ck_system_setting_value_type",
        ),
    )

    op.create_index("idx_system_setting_category", "system_setting", ["category"])
    op.create_index("idx_system_setting_key", "system_setting", ["setting_key"])

    # D 模式优先：公网中转 / 隧道模式默认值。
    op.execute(
        """
        INSERT INTO system_setting
            (category, setting_key, setting_value, value_type, is_editable, is_secret, description)
        VALUES
            ('network', 'deployment_mode', 'relay_tunnel', 'string', true, false, '当前主部署模式：relay_tunnel=公网中转/隧道模式'),
            ('network', 'public_api_base_url', '', 'string', true, false, '对外 API 公网访问地址'),
            ('network', 'public_admin_base_url', '', 'string', true, false, '管理后台公网访问地址'),
            ('network', 'public_update_base_url', '', 'string', true, false, '热更新资源公网访问地址'),
            ('network', 'health_check_url', '', 'string', true, false, '公网健康检查地址'),

            ('network', 'reverse_proxy_enabled', 'true', 'bool', true, false, '是否启用反向代理模式'),
            ('network', 'reverse_proxy_url', '', 'string', true, false, '公网反向代理地址'),
            ('network', 'force_https', 'true', 'bool', true, false, '是否要求公网入口使用 HTTPS'),
            ('network', 'real_ip_header', 'X-Forwarded-For', 'string', true, false, '真实客户端 IP Header'),
            ('network', 'trusted_proxy_enabled', 'false', 'bool', true, false, '是否启用可信代理 IP 校验'),
            ('network', 'trusted_proxy_ips', '[]', 'json', true, false, '可信代理 IP 列表'),

            ('network', 'relay_enabled', 'true', 'bool', true, false, '是否启用公网中转/隧道'),
            ('network', 'relay_mode', 'frp', 'string', true, false, '中转/隧道模式：frp/wireguard/cloudflared/custom_gateway/manual'),
            ('network', 'relay_url', '', 'string', true, false, '公网中转访问地址'),
            ('network', 'relay_health_url', '', 'string', true, false, '中转健康检查地址'),
            ('network', 'home_node_id', 'home-main-001', 'string', true, false, '家庭服务器节点 ID'),
            ('network', 'home_node_name', '家庭主节点', 'string', true, false, '家庭服务器节点名称'),
            ('network', 'home_local_verify_url', 'http://127.0.0.1:8000', 'string', true, false, '家庭服务器本地 Verify 地址，仅管理员可见'),

            ('network', 'client_config_enabled', 'true', 'bool', true, false, '是否启用客户端网络配置下发'),
            ('network', 'config_version', '1', 'int', true, false, '客户端网络配置版本号'),
            ('network', 'pc_client_api_url', '', 'string', true, false, 'PC 中控推荐 API 地址'),
            ('network', 'android_client_api_url', '', 'string', true, false, '安卓脚本推荐 API 地址'),
            ('network', 'backup_api_urls', '[]', 'json', true, false, '备用 API 地址列表'),
            ('network', 'client_timeout_seconds', '15', 'int', true, false, '客户端请求超时时间，单位秒'),
            ('network', 'client_retry_count', '3', 'int', true, false, '客户端请求重试次数'),
            ('network', 'heartbeat_interval_seconds', '30', 'int', true, false, '客户端心跳间隔，单位秒'),
            ('network', 'allow_client_config_pull', 'true', 'bool', true, false, '是否允许客户端拉取远程网络配置'),
            ('network', 'allow_client_auto_failover', 'true', 'bool', true, false, '是否允许客户端自动切换备用地址')
        """
    )


def downgrade() -> None:
    op.drop_index("idx_system_setting_key", table_name="system_setting")
    op.drop_index("idx_system_setting_category", table_name="system_setting")
    op.drop_table("system_setting")