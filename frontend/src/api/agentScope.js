import http from './http'

export const agentScopeApi = {
  levelPolicies() {
    return http.get('/api/agents/scope/level-policies', {
      _skipAuthRedirect: true,
    })
  },

  businessProfile(agentId) {
    return http.get(`/api/agents/scope/${agentId}/business-profile`, {
      _skipAuthRedirect: true,
    })
  },

  updateBusinessProfile(agentId, data) {
    return http.patch(`/api/agents/scope/${agentId}/business-profile`, data, {
      _skipAuthRedirect: true,
    })
  },

  projectAuths(agentId) {
    return http.get(`/api/agents/scope/${agentId}/project-auths`, {
      _skipAuthRedirect: true,
    })
  },

  grantProjectAuth(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/project-auths`, data, {
      _skipAuthRedirect: true,
    })
  },

  updateProjectAuth(agentId, authId, data) {
    return http.patch(`/api/agents/scope/${agentId}/project-auths/${authId}`, data, {
      _skipAuthRedirect: true,
    })
  },

  revokeProjectAuth(agentId, authId) {
    return http.delete(`/api/agents/scope/${agentId}/project-auths/${authId}`, {
      _skipAuthRedirect: true,
    })
  },

  balance(agentId) {
    return http.get(`/api/agents/scope/${agentId}/balance`, {
      _skipAuthRedirect: true,
    })
  },

  transactions(agentId, params = {}) {
    return http.get(`/api/agents/scope/${agentId}/transactions`, {
      params,
      _skipAuthRedirect: true,
    })
  },

  recharge(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/recharge`, data, {
      _skipAuthRedirect: true,
    })
  },

  credit(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/credit`, data, {
      _skipAuthRedirect: true,
    })
  },

  freeze(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/freeze`, data, {
      _skipAuthRedirect: true,
    })
  },

  unfreeze(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/unfreeze`, data, {
      _skipAuthRedirect: true,
    })
  },

  resetPassword(agentId, data) {
    return http.post(`/api/agents/scope/${agentId}/password`, data, {
      _skipAuthRedirect: true,
    })
  },
}