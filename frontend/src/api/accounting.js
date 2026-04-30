/**
 * 文件位置: src/api/accounting.js
 * 名称: 账务中心 API
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.1.0
 * 功能说明:
 *   对接后端正式账务中心接口 /admin/api/accounting。
 *
 * 当前能力:
 *   - 账务总览
 *   - 点数账本
 *   - 代理钱包
 *   - 充值
 *   - 授信
 *   - 冻结授信
 *   - 解冻授信
 *   - 授权扣点快照
 *   - 删除用户返点记录
 *   - 初始化开发期账务基线
 *   - 运行账务对账
 *   - 对账批次列表
 *   - 对账批次详情
 */

import http from './http'

export const accountingApi = {
  overview() {
    return http.get('/admin/api/accounting/overview')
  },

  ledger(params = {}) {
    return http.get('/admin/api/accounting/ledger', { params })
  },

  wallets(params = {}) {
    return http.get('/admin/api/accounting/wallets', { params })
  },

  walletDetail(agentId) {
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

  charges(params = {}) {
    return http.get('/admin/api/accounting/charges', { params })
  },

  refunds(params = {}) {
    return http.get('/admin/api/accounting/refunds', { params })
  },

  initReconciliationBaseline(params = {}) {
    return http.post('/admin/api/accounting/reconciliation/init-baseline', null, { params })
  },

  runReconciliation(params = {}) {
    return http.post('/admin/api/accounting/reconciliation/run', null, { params })
  },

  reconciliationRuns(params = {}) {
    return http.get('/admin/api/accounting/reconciliation/runs', { params })
  },

  reconciliationRunDetail(runId, params = {}) {
    return http.get(`/admin/api/accounting/reconciliation/runs/${runId}`, { params })
  },
}