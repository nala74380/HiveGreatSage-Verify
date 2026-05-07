/**
 * 文件位置: src/main.js
 * 功能说明: Vue 3 应用入口
 *
 * 挂载顺序（重要）：
 *   1. createApp
 *   2. Pinia（store 必须在 router 前注册，因为路由守卫要用 useAuthStore）
 *   3. Router
 *   4. Element Plus + Icons
 *   5. mount('#app')
 *
 * 安全口径:
 *   - 启动时清理旧版 localStorage Token 遗留。
 *   - 监听其他标签页的 logout 事件，同步清理当前标签页 sessionStorage。
 */

import { createApp }  from 'vue'
import { createPinia } from 'pinia'
import ElementPlus    from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn           from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'

import App    from './App.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'
import { useAuthStore } from './stores/auth'
import { storage } from './utils/storage'

const app   = createApp(App)
const pinia = createPinia()

// 注册所有 Element Plus 图标（按需使用时可替换为手动注册）
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component)
}

app
  .use(pinia)
  .use(router)
  .use(ElementPlus, { locale: zhCn })

// Pinia 初始化之后立即加载设置，保证 format.js 第一次调用就能读到正确时区
useSettingsStore()

// 清理旧版 localStorage 认证遗留值，避免从历史版本升级后继续长期驻留 Token。
storage.clearLegacyLocalStorage()

// 跨标签页同步登出：其他标签页触发 logout 后，当前标签页清空 session 并跳回登录页。
storage.onAuthCleared(() => {
  const authStore = useAuthStore()
  authStore.$patch({
    token: null,
    role: null,
    userInfo: null,
  })
  storage.clearAll({ broadcast: false })

  if (window.location.pathname !== '/login') {
    router.replace('/login')
  }
})

app.mount('#app')
