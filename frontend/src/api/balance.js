/**
 * 文件位置: src/api/balance.js
 * 名称: 点数余额兼容 API 门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   兼容旧页面 import { balanceApi } from '@/api/balance' 的写法。
 *   实际实现已拆到：
 *     - src/api/admin/balance.js  管理员专用 /admin/api/*
 *     - src/api/agent/balance.js  代理专用 /api/agents/*
 *
 *   这样可以先治理“按调用方分层”的 API 边界，同时避免一次性大范围修改
 *   所有 Vue 页面 import 路径，降低开发阶段联动风险。
 *
 * 改进内容:
 *   V1.1.0 - 拆分 adminBalanceApi / agentBalanceApi，并保留兼容门面
 *   V1.0.0 - 初始点数余额与项目定价接口
 *
 * 调试信息:
 *   新页面优先直接引入 adminBalanceApi 或 agentBalanceApi；旧页面可继续使用 balanceApi。
 */
import { adminBalanceApi } from './admin/balance'
import { agentBalanceApi } from './agent/balance'

export { adminBalanceApi, agentBalanceApi }

export const balanceApi = {
  // ── 项目定价（Admin）──────────────────────────────────────
  getPrices: adminBalanceApi.getPrices,
  setPrice: adminBalanceApi.setPrice,
  deletePrice: adminBalanceApi.deletePrice,

  // ── 定价目录（Agent 查看）────────────────────────────────
  catalog: agentBalanceApi.catalog,

  // ── 代理余额（Admin 操作）────────────────────────────────
  getBalance: adminBalanceApi.getBalance,
  recharge: adminBalanceApi.recharge,
  credit: adminBalanceApi.credit,
  freeze: adminBalanceApi.freeze,
  unfreeze: adminBalanceApi.unfreeze,
  getTransactions: adminBalanceApi.getTransactions,

  // ── 代理列表（含余额+项目）────────────────────────────────
  agentsFull: adminBalanceApi.agentsFull,

  // ── 代理自查 ──────────────────────────────────────────────
  myBalance: agentBalanceApi.myBalance,
  myTransactions: agentBalanceApi.myTransactions,
}