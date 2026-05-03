/**
 * 文件位置: src/api/agent/balance.js
 * 名称: 代理端余额与流水 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-05-03
 * 版本: V2.0.0
 * 功能及相关说明:
 *   代理身份专用余额、流水接口。
 *   V2.0.0: 路径统一到 /api/agents/my/*。
 */
import http from '../http'

export const agentBalanceApi = {
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
