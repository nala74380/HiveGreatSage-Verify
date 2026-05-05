/**
 * 文件位置: src/api/agent.js
 * 功能说明: 代理管理相关接口
 *
 * 后端路由对照：
 *   POST  /api/agents/                  创建代理
 *   GET   /api/agents/                  查询代理列表
 *   GET   /api/agents/{id}              查询代理详情
 *   GET   /api/agents/{id}/subtree      查询代理子树
 *   PATCH /api/agents/{id}              更新代理
 *   GET   /api/agents/me                代理个人主页
 *   GET   /api/agents/my-projects       代理已授权项目
 *
 * 当前业务口径：
 *   - Agent.level 表示代理组织层级 / 代理树深度。
 *   - AgentBusinessProfile.tier_level 表示代理业务等级。
 *   - 用户数量只作为统计展示。
 *   - 代理商业约束由项目准入、项目授权、授权扣点、点数余额和风险状态控制。
 */

import http from './http'

export const agentApi = {
  /**
   * 创建代理（需管理员身份）
   * @param {{ username: string, password: string, parent_agent_id?: number|null, commission_rate?: number|null }} data
   */
  create(data) {
    return http.post('/api/agents/', data)
  },

  /**
   * 查询代理列表（分页 + 过滤）
   * @param {{ page?: number, page_size?: number, status?: string }} params
   */
  list(params = {}) {
    return http.get('/api/agents/', { params })
  },

  scopeList(params = {}) {
    return http.get('/api/agents/scope/list', { params, _skipAuthRedirect: true })
  },

  /**
   * 查询代理详情
   * @param {number} agentId
   */
  detail(agentId) {
    return http.get(`/api/agents/${agentId}`)
  },

  /**
   * 查询代理子树
   * 返回 root / total_agents / total_users。
   * total_agents 包含根代理本身，前端展示下级代理总数时需要 -1。
   */
  subtree(agentId) {
    return http.get(`/api/agents/${agentId}/subtree`)
  },

  /**
   * 更新代理基础信息
   * @param {number} agentId
   * @param {{ status?: string, commission_rate?: number|null }} data
   */
  update(agentId, data) {
    return http.patch(`/api/agents/${agentId}`, data)
  },

  /**
   * 删除代理
   * 注意：代理涉及用户、授权、流水，生产使用前应优先停用。
   */
  delete(agentId) {
    return http.delete(`/admin/api/agents/${agentId}`)
  },

  /**
   * 代理个人主页（Agent Token）
   */
  me() {
    return http.get('/api/agents/me')
  },

  /**
   * 代理获取自己已授权的项目列表（Agent Token）
   */
  myProjects() {
    return http.get('/api/agents/my-projects')
  },

  /**
   * 平台统计概览
   */
  dashboard() {
    return http.get('/admin/api/dashboard')
  },
}