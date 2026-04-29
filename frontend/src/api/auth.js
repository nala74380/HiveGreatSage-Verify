/**
 * 文件位置: src/api/auth.js
 * 功能说明: 认证相关接口
 *
 * 后端路由对照（严格对齐 app/routers/auth.py + app/routers/admin.py + app/routers/agents.py）：
 *
 *   管理员登录  POST /admin/api/auth/login
 *     Request:  AdminLoginRequest  { username, password }
 *     Response: AdminLoginResponse { access_token, token_type, expires_in, admin_id, username }
 *
 *   代理登录    POST /api/agents/auth/login
 *     Request:  AgentLoginRequest  { username, password }
 *     Response: AgentLoginResponse { access_token, token_type, expires_in, agent_id, username, level }
 *
 *   登出        POST /api/auth/logout   （需 Bearer + refresh_token）
 *     注意：管理后台 Admin/Agent Token 无 refresh_token，此接口暂不适用。
 *     登出直接清除本地存储即可。
 */

import http from './http'

export const authApi = {
  /**
   * 管理员登录
   * _skipAuthRedirect: true —— 代理账号登录时第一步尝试此接口会返回 401，
   * 不能让拦截器把这个 401 当作 Token 失效处理（否则代理登录流程会被截断）
   */
  adminLogin(data) {
    return http.post('/admin/api/auth/login', data, { _skipAuthRedirect: true })
  },

  /**
   * 代理登录
   * _skipAuthRedirect: true —— 防止登录失败时拦截器误将 401 当作 Token 失效
   */
  agentLogin(data) {
    return http.post('/api/agents/auth/login', data, { _skipAuthRedirect: true })
  },
}
