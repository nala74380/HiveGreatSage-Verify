/**
 * 文件位置: src/api/user.js
 * 名称: 用户 API 兼容门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   兼容旧页面 import { userApi } from '@/api/user' 的写法。
 *   实际实现已拆到：
 *     - src/api/shared/user.js  Admin / Agent 共用的 /api/users/*
 *     - src/api/admin/user.js   Admin 专用的 /admin/api/users/* 附加操作
 *
 * 改进内容:
 *   V1.1.0 - 拆分 sharedUserApi / adminUserApi，并保留兼容门面
 *   V1.0.0 - 初始用户管理相关接口
 *
 * 调试信息:
 *   新页面优先按调用方引入具体 API；旧页面可继续使用 userApi。
 */
import { adminUserApi } from './admin/user'
import { sharedUserApi } from './shared/user'

export { adminUserApi, sharedUserApi }

export const userApi = {
  create: sharedUserApi.create,
  list: sharedUserApi.list,
  detail: sharedUserApi.detail,
  update: sharedUserApi.update,
  grantAuth: sharedUserApi.grantAuth,
  revokeAuth: sharedUserApi.revokeAuth,

  // ── 设备绑定（后端 /admin/api/users/:id/devices）──────────
  deviceBindings: adminUserApi.deviceBindings,
  unbindDevice: adminUserApi.unbindDevice,

  // ── 删除（软删除）──────────────────────────────────────────
  delete: adminUserApi.delete,
}