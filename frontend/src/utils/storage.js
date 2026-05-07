/**
 * 文件位置: src/utils/storage.js
 * 功能说明: 后台认证会话存储封装
 *
 * 当前安全口径:
 *   1. Admin / Agent access_token 仅保存到 sessionStorage。
 *   2. role / userInfo 同样保存到 sessionStorage，避免浏览器长期驻留。
 *   3. 兼容清理旧版 localStorage 中遗留的 hgs_token / hgs_role / hgs_user_info。
 *   4. 登出或 Token 失效时，通过 localStorage 短事件通知其他标签页清理会话。
 *
 * 边界说明:
 *   - 当前仍是 Bearer Token 前端存储方案。
 *   - 更高安全等级应评估后端 HttpOnly Cookie + CSRF 防护方案。
 *   - sessionStorage 是标签页级别，刷新保留，关闭标签页后清空。
 */

const TOKEN_KEY     = 'hgs_token'
const ROLE_KEY      = 'hgs_role'
const USER_INFO_KEY = 'hgs_user_info'
const AUTH_EVENT_KEY = 'hgs_auth_event'

const readSession = (key) => sessionStorage.getItem(key) || null
const writeSession = (key, value) => sessionStorage.setItem(key, value)
const removeSession = (key) => sessionStorage.removeItem(key)
const removeLegacyLocal = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
  localStorage.removeItem(USER_INFO_KEY)
}

const broadcastAuthEvent = (type) => {
  const payload = JSON.stringify({
    type,
    at: Date.now(),
  })
  localStorage.setItem(AUTH_EVENT_KEY, payload)
  localStorage.removeItem(AUTH_EVENT_KEY)
}

export const storage = {
  // ── Token ─────────────────────────────────────────────────────
  getToken() {
    return readSession(TOKEN_KEY)
  },
  setToken(token) {
    writeSession(TOKEN_KEY, token)
    localStorage.removeItem(TOKEN_KEY)
  },
  removeToken() {
    removeSession(TOKEN_KEY)
    localStorage.removeItem(TOKEN_KEY)
  },

  // ── Role ──────────────────────────────────────────────────────
  getRole() {
    return readSession(ROLE_KEY)
  },
  setRole(role) {
    writeSession(ROLE_KEY, role)
    localStorage.removeItem(ROLE_KEY)
  },

  // ── UserInfo ──────────────────────────────────────────────────
  /**
   * Admin userInfo 结构：  { admin_id, username }
   * Agent userInfo 结构：  { agent_id, username, hierarchy_depth }
   */
  getUserInfo() {
    try {
      const raw = readSession(USER_INFO_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },
  setUserInfo(info) {
    writeSession(USER_INFO_KEY, JSON.stringify(info))
    localStorage.removeItem(USER_INFO_KEY)
  },

  // ── 会话清理 ─────────────────────────────────────────────────
  clearAll(options = {}) {
    const { broadcast = true } = options
    removeSession(TOKEN_KEY)
    removeSession(ROLE_KEY)
    removeSession(USER_INFO_KEY)
    removeLegacyLocal()

    if (broadcast) {
      broadcastAuthEvent('logout')
    }
  },

  /** 清理旧版 localStorage 遗留值，不广播登出事件。 */
  clearLegacyLocalStorage() {
    removeLegacyLocal()
  },

  /** 监听其他标签页发出的认证清理事件。 */
  onAuthCleared(callback) {
    const handler = (event) => {
      if (event.key !== AUTH_EVENT_KEY || !event.newValue) return

      try {
        const payload = JSON.parse(event.newValue)
        if (payload?.type === 'logout') {
          callback(payload)
        }
      } catch {
        // 忽略异常事件
      }
    }

    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  },
}
