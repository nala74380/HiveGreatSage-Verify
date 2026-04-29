/**
 * 文件位置: src/api/agent/balance.js
 * 名称: 代理端余额与定价目录 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.2
 * 功能及相关说明:
 *   代理身份专用余额与定价目录接口，只调用 /api/agents/*。
 *   与 src/api/admin/balance.js 分离，避免前端 API 层继续混用调用方边界。
 *
 *   路径策略：
 *     - 项目目录使用 /api/agents/my/catalog。
 *     - 不再优先使用 /api/agents/catalog，避免与 /api/agents/{agent_id} 动态路由发生冲突。
 *
 *   开发阶段策略：
 *     - 项目目录 / 我的余额 / 我的流水属于功能页数据接口。
 *     - 接口异常时不应直接触发全局退出登录。
 *     - 使用 _skipAuthRedirect: true，由页面自己提示错误。
 *
 * 改进内容:
 *   V1.0.2 - catalog 改用 /api/agents/my/catalog，规避 /api/agents/{agent_id} 路由冲突
 *   V1.0.1 - 为代理功能接口增加 _skipAuthRedirect，避免接口异常时误触发退出登录
 *   V1.0.0 - 从 src/api/balance.js 拆分代理端 API
 *
 * 调试信息:
 *   项目目录 Network 应出现 GET /api/agents/my/catalog。
 */
import http from '../http'

export const agentBalanceApi = {
  // ── 定价目录（Agent 查看）────────────────────────────────
  catalog() {
    return http.get('/api/agents/my/catalog', {
      _skipAuthRedirect: true,
    })
  },

  // ── 代理自查 ──────────────────────────────────────────────
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