/**
 * 文件位置: src/api/admin/project.js
 * 名称: 项目与代理项目授权 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-05-08
 * 版本: V1.1.0
 * 功能及相关说明:
 *   管理员专用项目 CRUD 与代理项目授权接口。
 *   shared 页面中的项目下拉需要同时服务 Admin / Agent：
 *     - Admin 身份读取 /admin/api/projects/
 *     - Agent 身份读取 /api/agents/my-projects
 *
 * 边界:
 *   - create/detail/update/disable 仍是管理员专用能力。
 *   - grant/list/update/revoke AgentProjectAuth 仍是管理员专用能力。
 *   - list(params) 为 shared 页面兼容入口，会根据当前 role 自动分流。
 *
 * 调试信息:
 *   若 Agent Token 调用 /admin/api/projects/ 返回 401，是后端正确拒绝；
 *   前端 shared 页面应调用 list() 自动分流到 /api/agents/my-projects。
 */
import http from '../http'
import { storage } from '@/utils/storage'

const normalizeAgentProjectListResponse = (res) => ({
  ...res,
  data: {
    projects: Array.isArray(res.data) ? res.data : [],
    total: Array.isArray(res.data) ? res.data.length : 0,
    page: 1,
    page_size: Array.isArray(res.data) ? res.data.length : 0,
  },
})

export const adminProjectApi = {
  // ── 项目 CRUD ────────────────────────────────────────────
  create(data) {
    return http.post('/admin/api/projects/', data)
  },

  /**
   * 项目列表。
   * Admin: 返回平台全部项目。
   * Agent: 返回当前代理已授权且未过期的项目，供 shared 用户/代理页面下拉使用。
   */
  async list(params = {}) {
    if (storage.getRole() === 'agent') {
      const res = await http.get('/api/agents/my-projects', {
        params,
        _skipAuthRedirect: true,
      })
      return normalizeAgentProjectListResponse(res)
    }

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
