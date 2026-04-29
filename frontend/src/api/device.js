/**
 * 文件位置: src/api/device.js
 * 功能说明: 设备数据相关接口
 *
 * 后端路由对照（严格对齐 app/routers/device.py）：
 *
 *   GET /api/device/list
 *     Response: DeviceListResponse { devices, total, online_count }
 *     devices 每项: { device_id, user_id, status, last_seen, game_data, is_online }
 *
 *   GET /api/device/data?device_fingerprint=xxx
 *     Response: DeviceDataResponse { device_id, user_id, status, last_seen, game_data, is_online, source }
 *
 * 权限说明：
 *   - 两个接口的 get_current_user 依赖只接受 User Token（终端用户）。
 *   - Admin / Agent Token 调用会返回 401（权限不足，非 Token 失效）。
 *   - 已配置 _skipAuthRedirect: true，401 时不跳登录页，由 useDevicePoller 静默处理。
 *   - Phase 2 将新增 /admin/api/devices/ 供管理后台直接调用。
 */

import http from './http'

export const deviceApi = {
  /**
   * 拉取设备状态列表
   * Admin / Agent Token 调用会收到 401，useDevicePoller 已做静默处理。
   * @returns {Promise}
   */
  list() {
    return http.get('/api/device/list', { _skipAuthRedirect: true })
  },

  /**
   * 拉取单台设备运行数据详情
   * @param {string} deviceFingerprint
   * @returns {Promise}
   */
  data(deviceFingerprint) {
    return http.get('/api/device/data', {
      params: { device_fingerprint: deviceFingerprint },
      _skipAuthRedirect: true,
    })
  },
}
