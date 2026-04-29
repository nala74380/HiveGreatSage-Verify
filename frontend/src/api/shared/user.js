/**
 * 文件位置: src/api/shared/user.js
 * 名称: 管理员/代理共用用户管理 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   /api/users/* 当前支持 Admin Token 与 Agent Token 两种调用方。
 *   该文件作为 shared 层，避免误归类为纯 Admin 或纯 Agent。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/user.js 拆分共用用户管理 API
 *
 * 调试信息:
 *   代理只能操作权限范围内用户，管理员可操作全量用户；权限边界由后端 service 强制。
 */
import http from '../http'

export const sharedUserApi = {
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
}