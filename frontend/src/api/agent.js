import http from './http'
import { storage } from '@/utils/storage'

const isAgentRole = () => storage.getRole() === 'agent'
const agentBase = (path) => isAgentRole() ? `/api/agents/scope${path}` : `/api/agents${path}`

export const agentApi = {
  create(data) {
    if (isAgentRole()) {
      return http.post('/api/agents/scope', data, { _skipAuthRedirect: true })
    }

    return http.post('/api/agents/', data)
  },

  list(params = {}) {
    return http.get('/api/agents/', { params })
  },

  /**
   * 代理端权限范围超级列表增强接口。
   *
   * 当前主要服务 AgentListPage.vue 的代理视角，
   * 在基础代理列表字段之外额外返回：
   * - business_profile
   * - balance
   * - authorized_projects[].user_count
   */
  scopeList(params = {}) {
    return http.get('/api/agents/scope/list', {
      params,
      _skipAuthRedirect: true,
    })
  },

  detail(agentId) {
    return http.get(agentBase(`/${agentId}`), {
      _skipAuthRedirect: isAgentRole(),
    })
  },

  subtree(agentId) {
    return http.get(agentBase(`/${agentId}/subtree`), {
      _skipAuthRedirect: isAgentRole(),
    })
  },

  update(agentId, data) {
    return http.patch(agentBase(`/${agentId}`), data, {
      _skipAuthRedirect: isAgentRole(),
    })
  },

  suspend(agentId) {
    return this.update(agentId, { status: 'suspended' })
  },

  delete(agentId) {
    return http.delete(`/api/agents/${agentId}`)
  },

  /**
   * 代理资料与轻量业务能力摘要。
   *
   * 当前用途：
   * - AgentProfile.vue 的资料主体
   * - 展示父代理、用户统计、已授权项目、业务能力字段
   *
   * 不包含：
   * - 钱包余额主数据（走 /api/agents/my/balance）
   * - 工作台聚合统计（走 /api/agents/me/dashboard）
   */
  me() {
    return http.get('/api/agents/me')
  },

  myProjects() {
    return http.get('/api/agents/my-projects')
  },

  /** 管理员端 Dashboard 聚合接口 */
  dashboard() {
    return http.get('/admin/api/dashboard')
  },

  /**
   * 代理端工作台聚合接口。
   *
   * 当前主要服务 DashboardView.vue，
   * 返回 agent / wallet / users / online_devices / projects /
   * expiring_auths / sub_agents / sub_expiring_auths 等工作台聚合块。
   * 与 /api/agents/me 的资料摘要职责不同。
   */
  agentDashboard() {
    return http.get('/api/agents/me/dashboard')
  },
}