/**
 * 文件位置: src/api/admin/balance.js
 * 名称: 管理端点数余额与项目定价 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   管理员专用余额与定价接口，只调用 /admin/api/*。
 *   与 src/api/agent/balance.js 分离，避免前端 API 层继续混用调用方边界。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/balance.js 拆分管理端 API
 *
 * 调试信息:
 *   若接口 401，确认当前浏览器登录身份为 admin。
 */
import http from '../http'

export const adminBalanceApi = {
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
}