/**
 * 文件位置: src/router/routes/shared.js
 * 功能说明: Admin 和 Agent 共用路由（登录后均可访问，数据范围由后端控制）
 *
 * 视图隔离原则：
 *   同一页面组件，Admin 调 Admin Token 拿全量数据，Agent 调 Agent Token 拿范围内数据。
 *   路由层不做隔离，隔离由各页面 useAuthStore().isAdmin 判断后调不同 API 实现。
 */

import DashboardLayout from '@/layouts/DashboardLayout.vue'

export const sharedRoutes = [
  {
    path: '/',
    component: DashboardLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/shared/DashboardView.vue'),
        meta: { requiresAuth: true, title: '总览' },
      },
      {
        path: 'users',
        name: 'UserList',
        component: () => import('@/views/shared/UserList.vue'),
        meta: { requiresAuth: true, title: '用户管理' },
      },
      {
        path: 'users/:id',
        name: 'UserDetail',
        component: () => import('@/views/shared/UserDetail.vue'),
        meta: { requiresAuth: true, title: '用户详情' },
      },
      {
        path: 'agents',
        name: 'AgentList',
        component: () => import('@/views/shared/AgentList.vue'),
        meta: { requiresAuth: true, title: '代理管理' },
      },
      {
        path: 'devices',
        name: 'DeviceList',
        component: () => import('@/views/shared/DeviceList.vue'),
        meta: { requiresAuth: true, title: '设备监控' },
      },
      {
        path: 'login-logs',
        name: 'LoginLogs',
        component: () => import('@/views/shared/LoginLogView.vue'),
        meta: { requiresAuth: true, title: '登录日志' },
      },
    ],
  },
]
