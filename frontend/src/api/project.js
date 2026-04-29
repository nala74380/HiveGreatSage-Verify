/**
 * 文件位置: src/api/project.js
 * 功能说明: 项目管理 + 代理项目授权接口
 *
 * 后端路由对照（严格对齐 app/routers/projects.py）：
 *
 *   POST   /admin/api/projects/                          创建项目
 *   GET    /admin/api/projects/                          项目列表
 *   GET    /admin/api/projects/{id}                      项目详情
 *   PATCH  /admin/api/projects/{id}                      更新项目
 *
 *   POST   /admin/api/agents/{agent_id}/project-auths/          授予代理项目授权
 *   GET    /admin/api/agents/{agent_id}/project-auths/          查询代理项目授权列表
 *   PATCH  /admin/api/agents/{agent_id}/project-auths/{auth_id} 更新授权
 *   DELETE /admin/api/agents/{agent_id}/project-auths/{auth_id} 停用授权
 */

import http from './http'

export const projectApi = {
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
  delete(projectId) {
    return http.delete(`/admin/api/projects/${projectId}`)
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
