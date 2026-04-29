/**
 * 文件位置: src/api/agent.js
 * 功能说明: 代理管理相关接口
 *
 * 后端路由对照（严格对齐 app/routers/agents.py）：
 *
 *   POST  /api/agents/             创建代理（需 Admin Token）
 *   GET   /api/agents/?page&page_size&status  查询代理列表（需 Admin Token）
 *   GET   /api/agents/{id}         查询代理详情（需 Admin Token）
 *   PATCH /api/agents/{id}         更新代理（需 Admin Token）
 *
 * 管理后台 Dashboard：
 *   GET   /admin/api/dashboard     平台统计概览（需 Admin Token）
 *
 * Phase 1 说明：代理只能由管理员创建（无代理自建子代理能力，Phase 2 实现）
 */

import http from './http'

export const agentApi = {
  /**
   * 创建代理（需管理员身份）
   * @param {{ username, password, parent_agent_id?, max_users?, commission_rate? }} data
   * @returns {Promise<AgentResponse>}
   */
  create(data) {
    return http.post('/api/agents/', data)
  },

  /**
   * 查询代理列表（分页 + 过滤，需管理员身份）
   * @param {{ page?, page_size?, status? }} params
   * @returns {Promise<{ agents, total, page, page_size }>}
   */
  list(params = {}) {
    return http.get('/api/agents/', { params })
  },

  /**
   * 查询代理详情（需管理员身份）
   * @param {number} agentId
   * @returns {Promise<AgentResponse>}
   */
  detail(agentId) {
    return http.get(`/api/agents/${agentId}`)
  },

  /**
   * 更新代理（PATCH，需管理员身份）
   * @param {number} agentId
   * @param {{ status?, max_users?, commission_rate? }} data
   * @returns {Promise<AgentResponse>}
   */
  update(agentId, data) {
    return http.patch(`/api/agents/${agentId}`, data)
  },

  delete(agentId) {
    return http.delete(`/admin/api/agents/${agentId}`)
  },

  /**
   * 代理个人主页（Agent Token）
   * 返回基本信息、用户配额、已授权项目、用户统计
   */
  me() {
    return http.get('/api/agents/me')
  },

  /**
   * 代理获取自己已授权的项目列表（Agent Token）
   * 用于前端在创建用户 / 用户项目授权时过滤可选项目
   * @returns {Promise<Array<{id, display_name, code_name, project_type, auth_valid_until}>>}
   */
  myProjects() {
    return http.get('/api/agents/my-projects')
  },

  /**
   * 平台统计概览（需管理员身份）
   * @returns {Promise<{ admin, total_users, total_agents, active_projects }>}
   */
  dashboard() {
    return http.get('/admin/api/dashboard')
  },
}
