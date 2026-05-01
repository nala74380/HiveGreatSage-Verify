r"""
文件位置: app/schemas/system_setting.py
文件名称: system_setting.py
作者: 蜂巢·大圣 (HiveGreatSage)
日期/时间: 2026-05-01
版本: V1.2.0
功能说明:
    系统设置相关 Pydantic Schema。

当前重点:
    - NetworkSettingsResponse
    - NetworkSettingsUpdateRequest
    - ClientNetworkConfigResponse
    - RuntimeDiagnosticsResponse
    - UrlTestRequest / UrlTestResponse

本版改进:
    V1.2.0:
        - 增加 D 模式连接策略字段:
          route_strategy
          direct_enabled
          direct_candidate_urls
          direct_health_url
          direct_min_success_count
          direct_failback_threshold
          relay_keepalive_after_direct
          preferred_route

设计说明:
    当前 D 模式已确认用于“家庭无公网 IP”的部署前提。
    因此默认策略为 relay_only，不默认启用直连。
"""

from pydantic import BaseModel, Field, field_validator


DEPLOYMENT_MODES = {"cloud_direct", "home_direct", "reverse_proxy", "relay_tunnel"}
RELAY_MODES = {"frp", "wireguard", "cloudflared", "custom_gateway", "manual"}
REAL_IP_HEADERS = {"X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP", "none"}

ROUTE_STRATEGIES = {
    "relay_only",
    "auto_direct_with_relay_fallback",
    "direct_only",
    "manual",
}

PREFERRED_ROUTES = {
    "relay",
    "direct",
    "auto",
}


def _validate_url_or_empty(value: str | None, field_name: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(f"{field_name} 必须以 http:// 或 https:// 开头")

    return value.rstrip("/")


class NetworkSettingsBase(BaseModel):
    deployment_mode: str = Field(default="relay_tunnel", description="部署模式")

    public_api_base_url: str = ""
    public_admin_base_url: str = ""
    public_update_base_url: str = ""
    health_check_url: str = ""

    reverse_proxy_enabled: bool = True
    reverse_proxy_url: str = ""
    force_https: bool = True
    real_ip_header: str = "X-Forwarded-For"
    trusted_proxy_enabled: bool = False
    trusted_proxy_ips: list[str] = Field(default_factory=list)

    relay_enabled: bool = True
    relay_mode: str = "frp"
    relay_url: str = ""
    relay_health_url: str = ""
    home_node_id: str = "home-main-001"
    home_node_name: str = "家庭主节点"
    home_local_verify_url: str = "http://127.0.0.1:8000"

    # D 模式连接策略。
    # 当前已确认 D 模式前提为“家庭无公网 IP”，因此默认 relay_only。
    route_strategy: str = "relay_only"
    direct_enabled: bool = False
    direct_candidate_urls: list[str] = Field(default_factory=list)
    direct_health_url: str = ""
    direct_min_success_count: int = 2
    direct_failback_threshold: int = 2
    relay_keepalive_after_direct: bool = True
    preferred_route: str = "relay"

    client_config_enabled: bool = True
    config_version: int = 1
    pc_client_api_url: str = ""
    android_client_api_url: str = ""
    backup_api_urls: list[str] = Field(default_factory=list)
    client_timeout_seconds: int = 15
    client_retry_count: int = 3
    heartbeat_interval_seconds: int = 30
    allow_client_config_pull: bool = True
    allow_client_auto_failover: bool = True

    @field_validator("deployment_mode")
    @classmethod
    def validate_deployment_mode(cls, value: str) -> str:
        if value not in DEPLOYMENT_MODES:
            raise ValueError("deployment_mode 必须是 cloud_direct/home_direct/reverse_proxy/relay_tunnel")
        return value

    @field_validator("relay_mode")
    @classmethod
    def validate_relay_mode(cls, value: str) -> str:
        if value not in RELAY_MODES:
            raise ValueError("relay_mode 必须是 frp/wireguard/cloudflared/custom_gateway/manual")
        return value

    @field_validator("real_ip_header")
    @classmethod
    def validate_real_ip_header(cls, value: str) -> str:
        if value not in REAL_IP_HEADERS:
            raise ValueError("real_ip_header 必须是 X-Forwarded-For/X-Real-IP/CF-Connecting-IP/none")
        return value

    @field_validator("route_strategy")
    @classmethod
    def validate_route_strategy(cls, value: str) -> str:
        if value not in ROUTE_STRATEGIES:
            raise ValueError("route_strategy 必须是 relay_only/auto_direct_with_relay_fallback/direct_only/manual")
        return value

    @field_validator("preferred_route")
    @classmethod
    def validate_preferred_route(cls, value: str) -> str:
        if value not in PREFERRED_ROUTES:
            raise ValueError("preferred_route 必须是 relay/direct/auto")
        return value

    @field_validator(
        "public_api_base_url",
        "public_admin_base_url",
        "public_update_base_url",
        "health_check_url",
        "reverse_proxy_url",
        "relay_url",
        "relay_health_url",
        "home_local_verify_url",
        "pc_client_api_url",
        "android_client_api_url",
        "direct_health_url",
    )
    @classmethod
    def validate_url_fields(cls, value: str, info) -> str:
        return _validate_url_or_empty(value, info.field_name)

    @field_validator("backup_api_urls")
    @classmethod
    def validate_backup_api_urls(cls, value: list[str]) -> list[str]:
        result = []
        for item in value:
            result.append(_validate_url_or_empty(item, "backup_api_urls"))
        return [item for item in result if item]

    @field_validator("direct_candidate_urls")
    @classmethod
    def validate_direct_candidate_urls(cls, value: list[str]) -> list[str]:
        result = []
        for item in value:
            result.append(_validate_url_or_empty(item, "direct_candidate_urls"))
        return [item for item in result if item]

    @field_validator("client_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value < 3 or value > 120:
            raise ValueError("client_timeout_seconds 建议范围为 3~120 秒")
        return value

    @field_validator("client_retry_count")
    @classmethod
    def validate_retry(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("client_retry_count 建议范围为 1~10")
        return value

    @field_validator("heartbeat_interval_seconds")
    @classmethod
    def validate_heartbeat(cls, value: int) -> int:
        if value < 10 or value > 300:
            raise ValueError("heartbeat_interval_seconds 建议范围为 10~300 秒")
        return value

    @field_validator("direct_min_success_count")
    @classmethod
    def validate_direct_min_success_count(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("direct_min_success_count 建议范围为 1~10")
        return value

    @field_validator("direct_failback_threshold")
    @classmethod
    def validate_direct_failback_threshold(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("direct_failback_threshold 建议范围为 1~10")
        return value


class NetworkSettingsResponse(NetworkSettingsBase):
    updated_at: str | None = None
    updated_by_admin_id: int | None = None


class NetworkSettingsUpdateRequest(NetworkSettingsBase):
    pass


class ClientNetworkConfigResponse(BaseModel):
    config_version: int
    deployment_mode: str

    primary_api_url: str
    pc_client_api_url: str
    android_client_api_url: str
    backup_api_urls: list[str]

    timeout_seconds: int
    retry_count: int
    heartbeat_interval_seconds: int

    relay_enabled: bool
    relay_mode: str
    relay_url: str

    route_strategy: str
    direct_enabled: bool
    direct_candidate_urls: list[str]
    direct_health_url: str
    direct_min_success_count: int
    direct_failback_threshold: int
    relay_keepalive_after_direct: bool
    preferred_route: str


class UrlTestRequest(BaseModel):
    target_name: str = Field(default="目标地址", max_length=64)
    url: str
    timeout_seconds: int = Field(default=10, ge=3, le=120)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_url_or_empty(value, "url")


class UrlTestResponse(BaseModel):
    target_name: str
    url: str
    success: bool
    status_code: int | None = None
    elapsed_ms: int | None = None
    final_url: str | None = None
    error: str | None = None
    checked_at: str


class RuntimeDiagnosticsResponse(BaseModel):
    status: str
    server_time: str
    environment: str
    backend_timezone: str

    database_status: str
    database_error: str | None = None
    redis_status: str
    redis_error: str | None = None

    network_settings_loaded: bool
    deployment_mode: str

    public_api_base_url: str
    public_admin_base_url: str
    public_update_base_url: str

    relay_enabled: bool
    relay_mode: str
    relay_url: str
    relay_health_url: str

    route_strategy: str
    direct_enabled: bool
    direct_candidate_urls: list[str]
    direct_health_url: str
    preferred_route: str

    reverse_proxy_enabled: bool
    reverse_proxy_url: str
    real_ip_header: str
    trusted_proxy_enabled: bool

    request_remote_addr: str | None = None
    x_forwarded_for: str | None = None
    x_real_ip: str | None = None
    cf_connecting_ip: str | None = None
    selected_real_ip_value: str | None = None