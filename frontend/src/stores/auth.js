/**
 * 文件位置: src/stores/auth.js
 * 功能说明: 认证状态管理（Pinia）
 *
 * 登录流程说明：
 *   管理后台有两种身份入口，共用同一个登录页：
 *   1. 管理员：POST /admin/api/auth/login → AdminLoginResponse
 *      存储：role='admin', userInfo={ admin_id, username }
 *   2. 代理：  POST /api/agents/auth/login → AgentLoginResponse
 *      存储：role='agent', userInfo={ agent_id, username, level }
 *
 *   登录时先尝试管理员接口，若返回 401/422 再尝试代理接口。
 *   两者均失败则抛出错误，由登录页展示提示。
 */

import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { storage } from '@/utils/storage'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    /** @type {string|null} */
    token: storage.getToken(),
    /** @type {'admin'|'agent'|null} */
    role: storage.getRole(),
    /**
     * Admin:  { admin_id: number, username: string }
     * Agent:  { agent_id: number, username: string, level: number }
     * @type {object|null}
     */
    userInfo: storage.getUserInfo(),
  }),

  getters: {
    isLoggedIn: (s) => !!s.token,
    isAdmin:    (s) => s.role === 'admin',
    isAgent:    (s) => s.role === 'agent',
    displayName:(s) => s.userInfo?.username || '未知',
  },

  actions: {
    /**
     * 统一登录入口：先尝试 Admin，再尝试 Agent
     * @param {{ username: string, password: string }} credentials
     * @throws {Error} 两种身份均失败时抛出错误
     */
    async login(credentials) {
      // ① 先尝试管理员登录
      // adminLogin 已加 _skipAuthRedirect，401/403/422 不会触发全局跳转
      try {
        const res = await authApi.adminLogin(credentials)
        const data = res.data
        this._saveSession('admin', data.access_token, {
          admin_id: data.admin_id,
          username: data.username,
        })
        return
      } catch (err) {
        const status = err.response?.status
        // 401/403/422 = 账号密码错误或权限不匹配 → 继续尝试代理登录
        if (status !== 401 && status !== 403 && status !== 422) {
          throw err  // 其他错误（5xx、网络超时）直接抛出
        }
      }

      // ② 再尝试代理登录
      // agentLogin 已加 _skipAuthRedirect，失败时不会跳转登录页
      const res = await authApi.agentLogin(credentials)
      const data = res.data
      this._saveSession('agent', data.access_token, {
        agent_id: data.agent_id,
        username: data.username,
        level: data.level,
      })
    },

    /** 登出：清除状态 + 本地存储 */
    logout() {
      this.token    = null
      this.role     = null
      this.userInfo = null
      storage.clearAll()
    },

    /** 内部：统一保存登录状态 */
    _saveSession(role, token, userInfo) {
      this.token    = token
      this.role     = role
      this.userInfo = userInfo
      storage.setToken(token)
      storage.setRole(role)
      storage.setUserInfo(userInfo)
    },
  },
})
