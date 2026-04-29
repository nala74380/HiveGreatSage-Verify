/**
 * 文件位置: src/api/client/device.js
 * 名称: 终端用户设备数据 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能及相关说明:
 *   PC 中控 / 安卓脚本用户态接口，只调用 /api/device/*。
 *   该组接口依赖 User Token，不适合 Admin / Agent 后台页面直接调用。
 *
 * 改进内容:
 *   V1.0.0 - 从 src/api/device.js 拆分终端用户设备接口
 *
 * 调试信息:
 *   Admin / Agent Token 调用本文件接口会返回 401，这是权限边界，不代表 Token 失效。
 */
import http from '../http'

export const clientDeviceApi = {
  list() {
    return http.get('/api/device/list', { _skipAuthRedirect: true })
  },

  data(deviceFingerprint) {
    return http.get('/api/device/data', {
      params: { device_fingerprint: deviceFingerprint },
      _skipAuthRedirect: true,
    })
  },
}