/**
 * 文件位置: src/stores/settings.js
 * 功能说明: 系统设置状态管理（持久化到 localStorage）
 *
 * 当前支持的设置项：
 *   timezone — 显示时区，默认 Asia/Shanghai（UTC+8）
 *
 * 后续 Phase 2+ 扩展：
 *   networkRelay  — 网络中转地址
 *   reverseProxy  — 反代配置
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'hgs_settings'

const DEFAULTS = {
  timezone: 'Asia/Shanghai',
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULTS }
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = loadFromStorage()

  const timezone = ref(saved.timezone)

  // 自动持久化
  watch(
    () => ({ timezone: timezone.value }),
    (val) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
    },
    { deep: true },
  )

  function reset() {
    timezone.value = DEFAULTS.timezone
  }

  return { timezone, reset }
})
