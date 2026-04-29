/**
 * 文件位置: src/router/routes/admin.js
 * 功能说明: Admin 专属路由（meta.requiresAdmin = true）
 *
 * 这里的页面只有 role='admin' 才能访问。
 * 路由守卫在 router/index.js 中统一拦截。
 */

import DashboardLayout from '@/layouts/DashboardLayout.vue'

export const adminRoutes = [
  {
    path: '/',
    component: DashboardLayout,
    meta: { requiresAdmin: true },
    children: [
      {
        path: 'projects',
        name: 'GameProjectList',
        component: () => import('@/views/admin/GameProjectList.vue'),
        meta: { requiresAdmin: true, title: '项目管理' },
      },
      {
        path: 'updates',
        name: 'UpdateManage',
        component: () => import('@/views/admin/UpdateManage.vue'),
        meta: { requiresAdmin: true, title: '热更新' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/admin/SettingsView.vue'),
        meta: { requiresAdmin: true, title: '系统设置' },
      },
    ],
  },
]
