/**
 * 文件位置: src/utils/format.js
 * 功能说明: 时间、状态、用户级别等格式化工具函数
 *
 * 时区说明：
 *   后端 API 返回的 datetime 均为 UTC（ISO 8601 含 +00:00 或 Z）。
 *   前端显示时区由 useSettingsStore().timezone 动态控制，默认 Asia/Shanghai。
 *   修改设置后所有时间格式化函数立即生效（响应式读取）。
 */

import { useSettingsStore } from '@/stores/settings'

/** 获取当前展示时区（响应式，从 settingsStore 读取） */
function getTimezone() {
  try {
    // 在 Pinia 已初始化之后调用才有效；组件外调用时回退到默认值
    const store = useSettingsStore()
    return store.timezone || 'Asia/Shanghai'
  } catch {
    return 'Asia/Shanghai'
  }
}

// ── 时间格式化 ─────────────────────────────────────────────────

/**
 * ISO 字符串 → 当前时区的完整日期时间
 * @param {string|null} iso
 * @returns {string}
 */
export function formatDatetime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    timeZone: getTimezone(),
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
}

/**
 * ISO 字符串 → 当前时区的仅日期
 * @param {string|null} iso
 * @returns {string}
 */
export function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', {
    timeZone: getTimezone(),
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
}

/**
 * 计算距今的相对时间（设备心跳用）
 * @param {string|null} iso
 * @returns {string}
 */
export function formatRelativeTime(iso) {
  if (!iso) return '从未'
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60)    return `${sec} 秒前`
  if (sec < 3600)  return `${Math.floor(sec / 60)} 分钟前`
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`
  return `${Math.floor(sec / 86400)} 天前`
}

/**
 * 计算距今天数（正数=未来，负数=已过期）
 * @param {string|Date|null} val
 * @returns {number|null}
 */
export function daysFromNow(val) {
  if (!val) return null
  const diff = new Date(val).getTime() - Date.now()
  return Math.ceil(diff / 86_400_000)
}

/**
 * 到期时间 Tag 类型（el-tag :type）
 */
export function expiryTagType(iso) {
  const days = daysFromNow(iso)
  if (days === null) return 'info'
  if (days < 0)   return 'danger'
  if (days <= 7)  return 'danger'
  if (days <= 30) return 'warning'
  return 'success'
}

/**
 * 到期时间 Tag 文字
 */
export function expiryLabel(iso) {
  const days = daysFromNow(iso)
  if (days === null) return ''
  if (days < 0)   return `已过期 ${Math.abs(days)} 天`
  if (days === 0) return '今天到期'
  return `剩余 ${days} 天`
}

// ── 用户状态 ───────────────────────────────────────────────────

export const USER_STATUS_MAP = {
  active:    { label: '正常',   type: 'success' },
  suspended: { label: '已停用', type: 'danger' },
  expired:   { label: '已过期', type: 'info' },
}

export function formatUserStatus(status, user) {
  // 已停用优先
  if (status === 'suspended') return USER_STATUS_MAP.suspended
  // 检查是否所有授权都已过期
  if (user) {
    const auths = user.authorizations || []
    const hasActive = auths.some(a => a.status === 'active' && !a.is_expired)
    if (!hasActive && auths.length > 0) return USER_STATUS_MAP.expired
  }
  return USER_STATUS_MAP[status] || { label: status, type: 'info' }
}

// ── 用户级别 ───────────────────────────────────────────────────

export const USER_LEVEL_MAP = {
  trial:   { label: '试用',  color: '#909399' },
  normal:  { label: '普通',  color: '#409EFF' },
  vip:     { label: 'VIP',   color: '#E6A23C' },
  svip:    { label: 'SVIP',  color: '#F56C6C' },
  tester:  { label: '测试',  color: '#67C23A' },
}

export function formatUserLevel(level) {
  return USER_LEVEL_MAP[level] || { label: level, color: '#909399' }
}

// ── 设备状态 ───────────────────────────────────────────────────

export const DEVICE_STATUS_MAP = {
  running: { label: '运行中', type: 'success' },
  idle:    { label: '空闲',   type: 'warning' },
  error:   { label: '错误',   type: 'danger' },
  offline: { label: '离线',   type: 'info' },
}

export function formatDeviceStatus(status, isOnline) {
  if (!isOnline) return DEVICE_STATUS_MAP.offline
  return DEVICE_STATUS_MAP[status] || { label: status, type: 'info' }
}

// ── 代理状态 ───────────────────────────────────────────────────

export const AGENT_STATUS_MAP = {
  active:    { label: '正常',   type: 'success' },
  suspended: { label: '已停用', type: 'danger' },
}

export function formatAgentStatus(status) {
  return AGENT_STATUS_MAP[status] || { label: status, type: 'info' }
}
