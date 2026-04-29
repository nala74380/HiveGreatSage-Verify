/**
 * 文件位置: src/utils/storage.js
 * 功能说明: Token 和用户信息的 localStorage 读写封装
 *
 * 存储结构：
 *   hgs_token     — access_token 字符串
 *   hgs_role      — 'admin' | 'agent'
 *   hgs_user_info — JSON 序列化的用户信息对象
 *
 * 注意：Admin / Agent Token 没有 refresh_token，过期直接跳登录页。
 */

const TOKEN_KEY     = 'hgs_token'
const ROLE_KEY      = 'hgs_role'
const USER_INFO_KEY = 'hgs_user_info'

export const storage = {
  // ── Token ─────────────────────────────────────────────────────
  getToken() {
    return localStorage.getItem(TOKEN_KEY) || null
  },
  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token)
  },
  removeToken() {
    localStorage.removeItem(TOKEN_KEY)
  },

  // ── Role ──────────────────────────────────────────────────────
  getRole() {
    return localStorage.getItem(ROLE_KEY) || null
  },
  setRole(role) {
    localStorage.setItem(ROLE_KEY, role)
  },

  // ── UserInfo ──────────────────────────────────────────────────
  /**
   * Admin userInfo 结构：  { admin_id, username }
   * Agent userInfo 结构：  { agent_id, username, level }
   */
  getUserInfo() {
    try {
      const raw = localStorage.getItem(USER_INFO_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },
  setUserInfo(info) {
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(info))
  },

  // ── 一次性清空（登出时调用）──────────────────────────────────
  clearAll() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(USER_INFO_KEY)
  },
}
