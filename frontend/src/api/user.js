/**
 * 文件位置: src/api/user.js
 * 名称: 用户 API 统一出口
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.3.0
 * 功能及相关说明:
 *   用户管理接口统一出口。
 *
 * 核心口径:
 *   - User 是账号主体。
 *   - Authorization 是用户在某项目下的授权记录。
 *   - 项目内等级、授权设备数、到期时间全部归属 Authorization。
 *
 * 改进内容:
 *   V1.3.0 - 新增项目授权更新、创建者代理详情接口
 *   V1.2.0 - 新增 updatePassword
 *   V1.1.0 - 拆分 sharedUserApi / adminUserApi，并保留兼容门面
 */

import http from './http'
import { adminUserApi } from './admin/user'
import { sharedUserApi } from './shared/user'

export { adminUserApi, sharedUserApi }

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

  delete: adminUserApi.delete,

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

  // ── 创建者详情 ────────────────────────────────────────────
  creatorAgentDetail(agentId, params = {}) {
    return http.get(`/api/users/creators/agents/${agentId}`, { params })
  },

  // ── 设备绑定，保留兼容 ────────────────────────────────────
  deviceBindings: adminUserApi.deviceBindings,
  unbindDevice: adminUserApi.unbindDevice,
}