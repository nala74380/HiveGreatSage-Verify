/**
 * 文件位置: src/api/user.js
 * 名称: 用户 API 统一出口
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.3.1
 * 功能及相关说明:
 *   用户管理接口统一出口。
 *
 * 核心口径:
 *   - User 是账号主体。
 *   - Authorization 是用户在某项目下的授权记录。
 *   - 项目内等级、授权设备数、到期时间全部归属 Authorization。
 *
 * 本版修复:
 *   - delete(userId) 改为调用 /api/users/{userId}
 *   - 代理端删除用户不再调用 /admin/api/users/{userId}
 *   - 避免代理 Token 调管理员接口导致自动退出登录
 */

import http from './http'
import { adminUserApi } from './admin/user'

export { adminUserApi }

export const userApi = {
  // ── 用户基础 ──────────────────────────────────────────────
  create(data) {
    return http.post('/api/users/', data)
  },

  list(params = {}) {
    return http.get('/api/users/', { params })
  },

  detail(userId, params = {}) {
    return http.get(`/api/users/${userId}`, { params })
  },

  update(userId, data) {
    return http.patch(`/api/users/${userId}`, data)
  },

  delete(userId) {
    return http.delete(`/api/users/${userId}`)
  },

  // ── 密码 ──────────────────────────────────────────────────
  updatePassword(userId, data) {
    return http.patch(`/api/users/${userId}/password`, data)
  },

  // ── 用户项目授权 ──────────────────────────────────────────
  grantAuth(userId, data) {
    return http.post(`/api/users/${userId}/authorizations`, data)
  },

  updateAuth(userId, authId, data) {
    return http.patch(`/api/users/${userId}/authorizations/${authId}`, data)
  },

  revokeAuth(userId, authId) {
    return http.delete(`/api/users/${userId}/authorizations/${authId}`)
  },

  upgradeAuth(userId, authId, data) {
    return http.post(`/api/users/${userId}/authorizations/${authId}/upgrade`, data)
  },

  upgradePreview(userId, authId, additionalDevices, mode) {
    return http.get(`/api/users/${userId}/authorizations/${authId}/upgrade/preview`, {
      params: { additional_devices: additionalDevices, mode },
    })
  },

  // ── 创建者详情 ────────────────────────────────────────────
  creatorAgentDetail(agentId, params = {}) {
    return http.get(`/api/users/creators/agents/${agentId}`, { params })
  },

  // ── 管理员设备操作，保留管理员专用接口 ───────────────────
  deviceBindings: adminUserApi.deviceBindings,
  unbindDevice: adminUserApi.unbindDevice,
}
