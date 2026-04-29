/**
 * 文件位置: src/api/balance.js
 * 名称: 点数余额兼容 API 门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.2.0
 * 功能及相关说明:
 *   兼容旧页面 import { balanceApi } from '@/api/balance'。
 */
import { adminBalanceApi } from './admin/balance'
import { agentBalanceApi } from './agent/balance'

export { adminBalanceApi, agentBalanceApi }

export const balanceApi = {
  // Admin 全局流水
  globalTransactions: adminBalanceApi.globalTransactions,

  // 项目定价
  getPrices: adminBalanceApi.getPrices,
  setPrice: adminBalanceApi.setPrice,
  deletePrice: adminBalanceApi.deletePrice,

  // 代理目录
  catalog: agentBalanceApi.catalog,

  // 代理余额操作
  getBalance: adminBalanceApi.getBalance,
  recharge: adminBalanceApi.recharge,
  credit: adminBalanceApi.credit,
  freeze: adminBalanceApi.freeze,
  unfreeze: adminBalanceApi.unfreeze,
  getTransactions: adminBalanceApi.getTransactions,

  // 代理列表
  agentsFull: adminBalanceApi.agentsFull,

  // 代理自查
  myBalance: agentBalanceApi.myBalance,
  myTransactions: agentBalanceApi.myTransactions,
}