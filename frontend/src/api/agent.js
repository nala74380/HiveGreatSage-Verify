import http from './http'
import { storage } from '@/utils/storage'

const isAgentRole = () => storage.getRole() === 'agent'
const agentBase = (path) => isAgentRole() ? `/api/agents/scope${path}` : `/api/agents${path}`

export const agentApi = {
  create(data) {
    return http.post('/api/agents/', data)
  },

  list(params = {}) {
    return http.get('/api/agents/', { params })
  },

  scopeList(params = {}) {
    return http.get('/api/agents/scope/list', { params, _skipAuthRedirect: true })
  },

  detail(agentId) {
    return http.get(agentBase(`/${agentId}`), { _skipAuthRedirect: isAgentRole() })
  },

  subtree(agentId) {
    return http.get(agentBase(`/${agentId}/subtree`), { _skipAuthRedirect: isAgentRole() })
  },

  update(agentId, data) {
    return http.patch(agentBase(`/${agentId}`), data, { _skipAuthRedirect: isAgentRole() })
  },

  suspend(agentId) {
    return this.update(agentId, { status: 'suspended' })
  },

  me() {
    return http.get('/api/agents/me')
  },

  myProjects() {
    return http.get('/api/agents/my-projects')
  },

  dashboard() {
    return http.get('/admin/api/dashboard')
  },
}
