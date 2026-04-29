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
 *   GET   /api/agents/me           代理个人主页（需 Agent Token）
 *   GET   /api/agents/my-projects  代理已授权项目（需 Agent Token）
 *
 * 当前业务口径：
 *   - Agent.level 表示代理组织层级 / 代理树深度。
 *   - AgentBusinessProfile.tier_level 表示代理业务等级。
 *   - 用户数量只作为统计展示，不再作为代理配额限制。
 *   - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。
 */

import http from './http'

export const agentApi = {
  /**
   * 创建代理（需管理员身份）
   * @param {{ username: string, password: string, parent_agent_id?: number|null, commission_rate?: number|null }} data
   * @returns {Promise<AgentResponse>}
   */
  create(data) {
    return http.post('/api/agents/', data)
  },

  /**
   * 查询代理列表（分页 + 过滤，需管理员身份）
   * @param {{ page?: number, page_size?: number, status?: string }} params
   * @returns {Promise<{ agents: Array, total: number, page: number, page_size: number }>}
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
   * 更新代理基础信息（PATCH，需管理员身份）
   * @param {number} agentId
   * @param {{ status?: string, commission_rate?: number|null }} data
   * @returns {Promise<AgentResponse>}
   */
  update(agentId, data) {
    return http.patch(`/api/agents/${agentId}`, data)
  },

  /**
   * 删除代理（管理员接口）
   * 注意：删除代理涉及用户、授权、流水等关联数据，生产前建议改为停用优先。
   */
  delete(agentId) {
    return http.delete(`/admin/api/agents/${agentId}`)
  },

  /**
   * 代理个人主页（Agent Token）
   * 返回基本信息、用户统计、已授权项目。
   * 用户数量只作为统计展示。
   */
  me() {
    return http.get('/api/agents/me')
  },

  /**
   * 代理获取自己已授权的项目列表（Agent Token）
   * 用于前端在创建用户 / 用户项目授权时过滤可选项目。
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