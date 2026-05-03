/**
 * 文件位置: src/api/admin/balance.js
 * 名称: 管理端点数余额与项目定价 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-05-03
 * 版本: V2.0.0
 * 功能及相关说明:
 *   管理员专用余额、定价接口。
 *   V2.0.0: 旧路径迁移至 /admin/api/accounting/*。
 */
import http from '../http'

export const adminBalanceApi = {
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
    return http.get(`/admin/api/accounting/wallets/${agentId}`)
  },
  recharge(agentId, data) {
    return http.post(`/admin/api/accounting/agents/${agentId}/recharge`, data)
  },
  credit(agentId, data) {
    return http.post(`/admin/api/accounting/agents/${agentId}/credit`, data)
  },
  freeze(agentId, data) {
    return http.post(`/admin/api/accounting/agents/${agentId}/freeze`, data)
  },
  unfreeze(agentId, data) {
    return http.post(`/admin/api/accounting/agents/${agentId}/unfreeze`, data)
  },
  getTransactions(agentId, params = {}) {
    return http.get('/admin/api/accounting/ledger', {
      params: { agent_id: agentId, ...params },
    })
  },

  // ── 代理列表 ─────────────────────────────────────────────
  agentsFull(params = {}) {
    return http.get('/admin/api/accounting/agents-full', { params })
  },
}
