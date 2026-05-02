/**
 * 文件位置: src/api/admin/balance.js
 * 名称: 管理端点数余额与项目定价 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   管理员专用余额、定价、全局流水接口。
 */
import http from '../http'

export const adminBalanceApi = {
  // ── 管理员全局点数流水 ───────────────────────────────────
  // ── 项目定价 ─────────────────────────────────────────────
  getPrices(projectId) {
    return http.get(`/admin/api/prices/${projectId}`)
  },
  setPrice(projectId, userLevel, data) {
    return http.put(`/admin/api/prices/${projectId}/${userLevel}`, data)
  },
  deletePrice(projectId, userLevel) {
    return http.delete(`/admin/api/prices/${projectId}/${userLevel}`)
  },

  // ── 代理余额操作 ─────────────────────────────────────────
  getBalance(agentId) {
    return http.get(`/admin/api/agents/${agentId}/balance`)
  },
  recharge(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/recharge`, data)
  },
  credit(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/credit`, data)
  },
  freeze(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/freeze`, data)
  },
  unfreeze(agentId, data) {
    return http.post(`/admin/api/agents/${agentId}/unfreeze`, data)
  },
  getTransactions(agentId, params = {}) {
    return http.get(`/admin/api/agents/${agentId}/transactions`, { params })
  },

  // ── 代理列表 ─────────────────────────────────────────────
  agentsFull(params = {}) {
    return http.get('/admin/api/agents-full', { params })
  },
}
