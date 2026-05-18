# Verify OpenAPI 路由清单 — 2026-05-18

**paths**: 112 | **schemas**: 96

| 方法 | 路径 | summary |
|------|------|---------|
| GET | /admin/api/accounting/agents-full | 代理列表含余额与项目授权 |
| POST | /admin/api/accounting/agents/{agent_id}/credit | 给代理授信 |
| POST | /admin/api/accounting/agents/{agent_id}/freeze | 冻结代理授信 |
| POST | /admin/api/accounting/agents/{agent_id}/recharge | 给代理充值点数 |
| POST | /admin/api/accounting/agents/{agent_id}/unfreeze | 解冻代理授信 |
| GET | /admin/api/accounting/authorization-freezes | 授权冻结权益记录 |
| GET | /admin/api/accounting/charges | 授权扣点快照 |
| GET | /admin/api/accounting/ledger | 点数账本 |
| GET | /admin/api/accounting/overview | 账务中心总览 |
| POST | /admin/api/accounting/reconciliation/init-baseline | 初始化开发期账务基线 |
| POST | /admin/api/accounting/reconciliation/run | 运行账务对账 |
| GET | /admin/api/accounting/reconciliation/runs | 对账批次列表 |
| GET | /admin/api/accounting/reconciliation/runs/{run_id} | 对账批次详情 |
| GET | /admin/api/accounting/refunds | 删除用户返点记录 |
| GET | /admin/api/accounting/wallets | 代理钱包列表 |
| GET | /admin/api/accounting/wallets/{agent_id} | 代理钱包详情 |
| GET | /admin/api/agent-level-policies | 代理等级策略列表 |
| PATCH | /admin/api/agent-level-policies/{level} | 更新代理等级策略 |
| GET | /admin/api/agents/{agent_id}/business-profile | 查询代理业务画像 |
| PATCH | /admin/api/agents/{agent_id}/business-profile | 更新代理业务画像 |
| POST | /admin/api/agents/{agent_id}/password | 管理员重置代理密码 |
| GET | /admin/api/agents/{agent_id}/project-auths/ | List Agent Auths Endpoint |
| POST | /admin/api/agents/{agent_id}/project-auths/ | Grant Agent Auth Endpoint |
| DELETE | /admin/api/agents/{agent_id}/project-auths/{auth_id} | Revoke Agent Auth Endpoint |
| PATCH | /admin/api/agents/{agent_id}/project-auths/{auth_id} | Update Agent Auth Endpoint |
| GET | /admin/api/audit-logs/ | 审计日志列表 |
| GET | /admin/api/audit-logs/{audit_log_id} | 审计日志详情 |
| POST | /admin/api/auth/login | Admin Login Endpoint |
| GET | /admin/api/dashboard | Admin Dashboard |
| GET | /admin/api/debug/device-bindings/{user_id} | Debug Device Bindings |
| GET | /admin/api/devices/ | 全平台设备普通分页列表（Admin / Agent 后台） |
| GET | /admin/api/devices/search | 高成本全局设备搜索（Admin / Agent 后台） |
| GET | /admin/api/devices/summary | 全平台设备统计摘要（Admin / Agent 后台） |
| GET | /admin/api/devices/{game_project_code} | 按项目查看设备监控 |
| GET | /admin/api/login-logs/ | List Login Logs |
| GET | /admin/api/prices/{project_id} | 获取项目各级别定价 |
| DELETE | /admin/api/prices/{project_id}/{user_level} | 删除单价 |
| PUT | /admin/api/prices/{project_id}/{user_level} | 设置/更新单价 |
| GET | /admin/api/project-access/policies | 项目准入策略列表 |
| PATCH | /admin/api/project-access/policies/{project_id} | 更新项目准入策略 |
| GET | /admin/api/project-access/requests | 代理项目开通申请列表 |
| POST | /admin/api/project-access/requests/{request_id}/approve | 批准代理项目开通申请 |
| POST | /admin/api/project-access/requests/{request_id}/reject | 拒绝代理项目开通申请 |
| GET | /admin/api/projects/ | List Projects Endpoint |
| POST | /admin/api/projects/ | Create Project Endpoint |
| GET | /admin/api/projects/{project_id} | Get Project Endpoint |
| PATCH | /admin/api/projects/{project_id} | Update Project Endpoint |
| POST | /admin/api/session/logout | 管理员退出登录 |
| GET | /admin/api/system-settings/diagnostics | 系统运行诊断 |
| GET | /admin/api/system-settings/network | 读取网络设置 |
| PUT | /admin/api/system-settings/network | 保存网络设置 |
| POST | /admin/api/system-settings/test-url | 测试 URL 连通性 |
| POST | /admin/api/updates/{project_id}/{client_type} | 发布热更新包 |
| GET | /admin/api/updates/{project_id}/{client_type}/history | 版本历史 |
| GET | /admin/api/updates/{project_id}/{client_type}/latest | 获取当前活跃版本 |
| GET | /admin/api/users/{user_id}/devices | Get User Devices |
| DELETE | /admin/api/users/{user_id}/devices/{binding_id} | Unbind Device |
| GET | /api/agents/ | List Agents Endpoint |
| POST | /api/agents/ | Create Agent Endpoint |
| POST | /api/agents/auth/login | Agent Login Endpoint |
| GET | /api/agents/me | 代理个人主页 |
| GET | /api/agents/me/dashboard | 代理端总览（单次请求） |
| GET | /api/agents/my-projects | Get My Authorized Projects |
| GET | /api/agents/my/balance | 代理查询自己余额 |
| GET | /api/agents/my/project-access/catalog | 代理项目目录（带准入策略） |
| GET | /api/agents/my/project-access/requests | 我的项目开通申请 |
| POST | /api/agents/my/project-access/requests | 提交项目开通申请 / 满足条件时自动开通 |
| POST | /api/agents/my/project-access/requests/{request_id}/cancel | 取消我的待审核项目申请 |
| GET | /api/agents/my/transactions | 代理查询自己流水 |
| POST | /api/agents/scope | Create Agent In Scope Endpoint |
| GET | /api/agents/scope/level-policies | 代理端获取可设置的下级业务等级策略 |
| GET | /api/agents/scope/list | List Agents In Scope Endpoint |
| GET | /api/agents/scope/{agent_id} | Get Agent In Scope Endpoint |
| PATCH | /api/agents/scope/{agent_id} | Update Agent In Scope Endpoint |
| GET | /api/agents/scope/{agent_id}/balance | 代理端查看下级余额 |
| GET | /api/agents/scope/{agent_id}/business-profile | 代理端查看下级业务画像 |
| PATCH | /api/agents/scope/{agent_id}/business-profile | 代理端更新下级业务画像 |
| POST | /api/agents/scope/{agent_id}/credit | 代理端给下级划拨授信点数 |
| POST | /api/agents/scope/{agent_id}/freeze | 代理端冻结下级授信 |
| POST | /api/agents/scope/{agent_id}/password | 代理端重置下级代理密码 |
| GET | /api/agents/scope/{agent_id}/project-auths | 代理端查看下级项目授权 |
| POST | /api/agents/scope/{agent_id}/project-auths | 代理端给下级开通项目 |
| DELETE | /api/agents/scope/{agent_id}/project-auths/{auth_id} | 代理端停用下级项目授权 |
| PATCH | /api/agents/scope/{agent_id}/project-auths/{auth_id} | 代理端更新下级项目授权 |
| POST | /api/agents/scope/{agent_id}/recharge | 代理端给下级划拨充值点数 |
| GET | /api/agents/scope/{agent_id}/subtree | Get Agent Subtree In Scope Endpoint |
| GET | /api/agents/scope/{agent_id}/transactions | 代理端查看下级流水 |
| POST | /api/agents/scope/{agent_id}/unfreeze | 代理端解冻下级授信 |
| POST | /api/agents/session/logout | 代理退出登录 |
| GET | /api/agents/tree | Get Full Agent Tree |
| DELETE | /api/agents/{agent_id} | 管理员硬删除代理 |
| GET | /api/agents/{agent_id} | Get Agent Endpoint |
| PATCH | /api/agents/{agent_id} | Update Agent Endpoint |
| GET | /api/agents/{agent_id}/subtree | Get Agent Subtree Endpoint |
| POST | /api/auth/login | Login |
| POST | /api/auth/logout | Logout |
| GET | /api/auth/me | Get Me |
| POST | /api/auth/refresh | Refresh |
| POST | /api/auth/revoke-all | 踢出所有设备 |
| GET | /api/client/network-config | 客户端网络配置 |
| GET | /api/device/data | Device Data |
| POST | /api/device/heartbeat | Heartbeat |
| GET | /api/device/list | List Devices |
| GET | /api/params/get | 拉取脚本参数 |
| POST | /api/params/set | 保存脚本参数 |
| GET | /api/stats/agents/my/summary | Agent Project Summary |
| GET | /api/stats/platform | Platform Summary |
| GET | /api/stats/users/{user_id}/projects | User Project Stats |
| GET | /api/update/check | 检查版本更新 |
| GET | /api/update/download | 获取下载链接 |
| GET | /api/users/ | List Users Endpoint |
| POST | /api/users/ | Create User Endpoint |
| GET | /api/users/creators/agents/{agent_id} | Creator Agent Detail Endpoint |
| DELETE | /api/users/{user_id} | Delete User Endpoint |
| GET | /api/users/{user_id} | Get User Endpoint |
| PATCH | /api/users/{user_id} | Update User Endpoint |
| POST | /api/users/{user_id}/authorizations | Grant Auth Endpoint |
| POST | /api/users/{user_id}/authorizations/preview | 预览授权新项目扣点 |
| DELETE | /api/users/{user_id}/authorizations/{auth_id} | Revoke Auth Endpoint |
| POST | /api/users/{user_id}/authorizations/{auth_id}/devices/add | 新增授权设备 |
| GET | /api/users/{user_id}/authorizations/{auth_id}/devices/add/preview | 预览新增设备扣点 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/enable | 启用授权并恢复冻结权益 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/level-upgrade | 授权等级升级 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/level-upgrade/preview | 预览授权等级升级差价扣点 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/renew | 授权续费 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/renew/preview | 预览授权续费扣点 |
| POST | /api/users/{user_id}/authorizations/{auth_id}/suspend | 停用授权并冻结剩余权益 |
| PATCH | /api/users/{user_id}/password | Update User Password Endpoint |
| GET | /health | Health Check |
| GET | /health/workers | Worker Health Check |