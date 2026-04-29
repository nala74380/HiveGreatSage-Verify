/**
 * 文件位置: src/api/project.js
 * 名称: 项目 API 兼容门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   兼容旧页面 import { projectApi } from '@/api/project' 的写法。
 *   当前项目 CRUD 与代理项目授权均属于管理端能力，实际实现已拆到：
 *     - src/api/admin/project.js
 *
 * 改进内容:
 *   V1.1.0 - 拆分 adminProjectApi，并保留兼容门面
 *   V1.0.0 - 初始项目管理 + 代理项目授权接口
 *
 * 调试信息:
 *   新页面优先直接引入 adminProjectApi；旧页面可继续使用 projectApi。
 */
import { adminProjectApi } from './admin/project'

export { adminProjectApi }

export const projectApi = {
  create: adminProjectApi.create,
  list: adminProjectApi.list,
  detail: adminProjectApi.detail,
  update: adminProjectApi.update,
  delete: adminProjectApi.delete,
  grantAgentAuth: adminProjectApi.grantAgentAuth,
  listAgentAuths: adminProjectApi.listAgentAuths,
  updateAgentAuth: adminProjectApi.updateAgentAuth,
  revokeAgentAuth: adminProjectApi.revokeAgentAuth,
}