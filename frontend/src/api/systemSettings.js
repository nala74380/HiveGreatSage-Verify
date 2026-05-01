/**
 * 文件位置: src/api/systemSettings.js
 * 名称: 系统设置 API
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.1.0
 * 功能说明:
 *   对接后端系统设置接口。
 */

import http from './http'

export const systemSettingsApi = {
  getNetworkSettings() {
    return http.get('/admin/api/system-settings/network')
  },

  updateNetworkSettings(data) {
    return http.put('/admin/api/system-settings/network', data)
  },

  getDiagnostics() {
    return http.get('/admin/api/system-settings/diagnostics')
  },

  testUrl(data) {
    return http.post('/admin/api/system-settings/test-url', data)
  },
}