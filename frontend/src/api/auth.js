/**
 * 文件位置: src/api/auth.js
 * 功能说明: 认证相关接口
 *
 * 后端路由对照：
 *
 *   管理员登录  POST /admin/api/auth/login
 *   代理登录    POST /api/agents/auth/login
 *
 *   管理员登出  POST /admin/api/session/logout
 *   代理登出    POST /api/agents/session/logout
 *
 * 说明：
 *   Admin / Agent 后台 Token 无 refresh_token。
 *   登出时后端会将当前 access_token 的 jti 加入 Redis 黑名单。
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

  /** 管理员退出登录：服务端吊销当前 Admin Token。 */
  adminLogout() {
    return http.post('/admin/api/session/logout')
  },

  /** 代理退出登录：服务端吊销当前 Agent Token。 */
  agentLogout() {
    return http.post('/api/agents/session/logout')
  },
}
