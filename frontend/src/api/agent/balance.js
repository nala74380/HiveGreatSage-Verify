/**
 * 文件位置: src/api/agent/balance.js
 * 名称: 代理端余额与定价目录 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   代理身份专用余额、项目目录、流水接口。
 */
import http from '../http'

export const agentBalanceApi = {
  catalog() {
    return http.get('/api/agents/my/catalog', {
      _skipAuthRedirect: true,
    })
  },

  myBalance() {
    return http.get('/api/agents/my/balance', {
      _skipAuthRedirect: true,
    })
  },

  myTransactions(params = {}) {
    return http.get('/api/agents/my/transactions', {
      params,
      _skipAuthRedirect: true,
    })
  },
}