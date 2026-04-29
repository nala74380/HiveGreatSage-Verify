/**
 * 文件位置: src/api/device.js
 * 名称: 设备 API 兼容门面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   兼容旧页面 import { deviceApi } from '@/api/device' 的写法。
 *   实际实现已拆到：
 *     - src/api/admin/device.js   Admin / Agent 后台设备监控
 *     - src/api/client/device.js  User Token 终端设备接口
 *
 *   关键边界：
 *     - /admin/api/devices/* 可由 Admin / Agent 后台调用。
 *     - /api/device/* 只适合 PC 中控 / 安卓脚本的 User Token 调用。
 *
 * 改进内容:
 *   V1.1.0 - 拆分 adminDeviceApi / clientDeviceApi，并保留兼容门面
 *   V1.0.0 - 初始设备接口
 *
 * 调试信息:
 *   管理后台设备页应使用 adminDeviceApi；终端客户端使用 clientDeviceApi。
 */
import { adminDeviceApi } from './admin/device'
import { clientDeviceApi } from './client/device'

export { adminDeviceApi, clientDeviceApi }

export const deviceApi = {
  // 兼容旧命名：用户态设备列表
  list: clientDeviceApi.list,
  data: clientDeviceApi.data,

  // 新命名：后台设备监控
  adminListAll: adminDeviceApi.listAll,
  adminListByProject: adminDeviceApi.listByProject,
  adminUserBindings: adminDeviceApi.userBindings,
  adminUnbindUserDevice: adminDeviceApi.unbindUserDevice,
}