/**
 * 文件位置: src/api/balance.js
 * 功能说明: 点数余额与项目定价接口
 */
import http from './http'

export const balanceApi = {
  // ── 项目定价（Admin）──────────────────────────────────────
  getPrices(projectId) {
    return http.get(`/admin/api/prices/${projectId}`)
  },
  setPrice(projectId, userLevel, data) {
    return http.put(`/admin/api/prices/${projectId}/${userLevel}`, data)
  },
  deletePrice(projectId, userLevel) {
    return http.delete(`/admin/api/prices/${projectId}/${userLevel}`)
  },

  // ── 定价目录（Agent 查看）────────────────────────────────
  catalog() {
    return http.get('/api/agents/catalog')
  },

  // ── 代理余额（Admin 操作）────────────────────────────────
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

  // ── 代理列表（含余额+项目）────────────────────────────────
  agentsFull(params = {}) {
    return http.get('/admin/api/agents-full', { params })
  },

  // ── 代理自查 ──────────────────────────────────────────────
  myBalance() {
    return http.get('/api/agents/my/balance')
  },
  myTransactions(params = {}) {
    return http.get('/api/agents/my/transactions', { params })
  },
}
