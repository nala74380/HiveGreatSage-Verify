/**
 * 文件位置: src/api/agent/balance.js
 * 名称: 代理端余额与定价目录 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   代理身份专用余额与定价目录接口，只调用 /api/agents/*。
 *   与 src/api/admin/balance.js 分离，避免前端 API 层继续混用调用方边界。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/balance.js 拆分代理端 API
 *
 * 调试信息:
 *   若接口 401，确认当前浏览器登录身份为 agent。
 */
import http from '../http'

export const agentBalanceApi = {
  // ── 定价目录（Agent 查看）────────────────────────────────
  catalog() {
    return http.get('/api/agents/catalog')
  },

  // ── 代理自查 ──────────────────────────────────────────────
  myBalance() {
    return http.get('/api/agents/my/balance')
  },
  myTransactions(params = {}) {
    return http.get('/api/agents/my/transactions', { params })
  },
}