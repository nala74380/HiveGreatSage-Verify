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

app.mount('#app')
