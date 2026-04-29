/**
 * 文件位置: src/api/admin/user.js
 * 名称: 管理端用户附加操作 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   管理员专用用户附加操作，例如设备绑定查看、解绑、软删除。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/user.js 拆分管理端用户附加操作
 *
 * 调试信息:
 *   若接口 401，确认当前浏览器登录身份为 admin。
 */
import http from '../http'

export const adminUserApi = {
  deviceBindings(userId) {
    return http.get(`/admin/api/users/${userId}/devices`)
  },
  unbindDevice(userId, bindingId) {
    return http.delete(`/admin/api/users/${userId}/devices/${bindingId}`)
  },
  delete(userId) {
    return http.delete(`/admin/api/users/${userId}`)
  },
}