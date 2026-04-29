/**
 * 文件位置: src/api/user.js
 * 功能说明: 用户管理相关接口
 */

import http from './http'

export const userApi = {
  create(data) {
    return http.post('/api/users/', data)
  },
  list(params = {}) {
    return http.get('/api/users/', { params })
  },
  detail(userId) {
    return http.get(`/api/users/${userId}`)
  },
  update(userId, data) {
    return http.patch(`/api/users/${userId}`, data)
  },
  grantAuth(userId, data) {
    return http.post(`/api/users/${userId}/authorizations`, data)
  },
  revokeAuth(userId, authId) {
    return http.delete(`/api/users/${userId}/authorizations/${authId}`)
  },
  // ── 设备绑定（后端 /admin/api/users/:id/devices）──────────
  deviceBindings(userId) {
    return http.get(`/admin/api/users/${userId}/devices`)
  },
  unbindDevice(userId, bindingId) {
    return http.delete(`/admin/api/users/${userId}/devices/${bindingId}`)
  },
  // ── 删除（软删除）──────────────────────────────────────────
  delete(userId) {
    return http.delete(`/admin/api/users/${userId}`)
  },
}
