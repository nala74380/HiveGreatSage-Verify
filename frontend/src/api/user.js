/**
 * 文件位置: src/api/user.js
 * 名称: 用户 API 兼容门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.2.0
 * 功能及相关说明:
 *   用户管理接口统一出口。
 *   兼容旧页面 import { userApi } from '@/api/user'。
 *
 * 改进内容:
 *   V1.2.0 - 新增 updatePassword
 *   V1.1.0 - 拆分 sharedUserApi / adminUserApi，并保留兼容门面
 */

import http from './http'
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

  updatePassword(userId, data) {
    return http.patch(`/api/users/${userId}/password`, data)
  },

  deviceBindings: adminUserApi.deviceBindings,
  unbindDevice: adminUserApi.unbindDevice,
  delete: adminUserApi.delete,
}