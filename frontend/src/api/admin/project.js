/**
 * 文件位置: src/api/admin/project.js
 * 名称: 管理端项目与代理项目授权 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   管理员专用项目 CRUD 与代理项目授权接口。
 *   统一调用 /admin/api/*，避免项目管理能力散落在通用 API 文件中。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/project.js 拆分管理端项目 API
 *
 * 调试信息:
 *   若接口 401，确认当前浏览器登录身份为 admin。
 */
import http from '../http'

export const adminProjectApi = {
  // ── 项目 CRUD ────────────────────────────────────────────
  create(data) {
    return http.post('/admin/api/projects/', data)
  },
  list(params = {}) {
    return http.get('/admin/api/projects/', { params })
  },
  detail(projectId) {
    return http.get(`/admin/api/projects/${projectId}`)
  },
  update(projectId, data) {
    return http.patch(`/admin/api/projects/${projectId}`, data)
  },
  disable(projectId) {
    return http.patch(`/admin/api/projects/${projectId}`, { is_active: false })
  },

  // ── 代理项目授权 ─────────────────────────────────────────
  grantAgentAuth(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/project-auths/`, data)
  },
  listAgentAuths(agentId) {
    return http.get(`/admin/api/agents/${agentId}/project-auths/`)
  },
  updateAgentAuth(agentId, authId, data) {
    return http.patch(`/admin/api/agents/${agentId}/project-auths/${authId}`, data)
  },
  revokeAgentAuth(agentId, authId) {
    return http.delete(`/admin/api/agents/${agentId}/project-auths/${authId}`)
  },
}