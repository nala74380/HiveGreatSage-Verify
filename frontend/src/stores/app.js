/**
 * 文件位置: src/stores/app.js
 * 功能说明: 全局 UI 状态管理（侧边栏折叠、加载状态等）
 */

import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    /** 侧边栏是否折叠 */
    sidebarCollapsed: false,
    /** 全局 loading（页面级） */
    globalLoading: false,
  }),

  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
    },
    setGlobalLoading(val) {
      this.globalLoading = val
    },
  },
})
