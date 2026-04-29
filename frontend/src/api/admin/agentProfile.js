/**
 * 文件位置: src/api/admin/agentProfile.js
 * 名称: 管理员代理业务管理 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   代理业务等级策略、代理业务画像、代理密码重置接口。
 */

import http from '../http'

export const adminAgentProfileApi = {
  levelPolicies() {
    return http.get('/admin/api/agent-level-policies')
  },

  updateLevelPolicy(level, data) {
    return http.patch(`/admin/api/agent-level-policies/${level}`, data)
  },

  businessProfile(agentId) {
    return http.get(`/admin/api/agents/${agentId}/business-profile`)
  },

  updateBusinessProfile(agentId, data) {
    return http.patch(`/admin/api/agents/${agentId}/business-profile`, data)
  },

  resetPassword(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/password`, data)
  },
}