/**
 * 文件位置: src/api/admin/device.js
 * 名称: 管理端设备监控 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   Admin / Agent 后台设备监控接口，只调用 /admin/api/devices/* 与
 *   /admin/api/users/{user_id}/devices。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/device.js 拆分后台设备接口
 *
 * 调试信息:
 *   后台设备页应优先调用本文件，不再调用 User Token 专用的 /api/device/*。
 */
import http from '../http'

export const adminDeviceApi = {
  listAll(params = {}) {
    return http.get('/admin/api/devices/', {
      params,
      _skipAuthRedirect: true,
    })
  },

  listByProject(gameProjectCode, params = {}) {
    return http.get(`/admin/api/devices/${gameProjectCode}`, {
      params,
      _skipAuthRedirect: true,
    })
  },

  userBindings(userId) {
    return http.get(`/admin/api/users/${userId}/devices`, {
      _skipAuthRedirect: true,
    })
  },

  unbindUserDevice(userId, bindingId) {
    return http.delete(`/admin/api/users/${userId}/devices/${bindingId}`)
  },
}